import math
from dataclasses import replace

from app.search import DEFAULT_CONFIG, ChunkRecord, SearchConfig, SearchIndex


def make_record(
    chunk_id: int,
    symbol_name: str,
    *,
    path: str = "pkg/module.py",
    symbol_type: str = "function",
    start_line: int = 1,
    end_line: int | None = None,
    docstring: str | None = None,
    source_code: str = "pass",
) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        path=path,
        symbol_name=symbol_name,
        symbol_type=symbol_type,
        start_line=start_line,
        end_line=end_line if end_line is not None else start_line,
        docstring=docstring,
        source_code=source_code,
    )


def names(results: list[ChunkRecord]) -> list[str]:
    return [record.symbol_name for record in results]


def test_search_returns_nothing_for_unknown_terms_and_empty_index() -> None:
    index = SearchIndex([make_record(1, "alpha")])
    assert index.search("zebra") == []
    assert SearchIndex([]).search("alpha") == []


def test_natural_language_query_matches_split_identifier() -> None:
    index = SearchIndex(
        [
            make_record(1, "get_encoding_from_headers"),
            make_record(2, "unrelated_helper"),
        ]
    )
    assert names(index.search("encoding from headers")) == ["get_encoding_from_headers"]


def test_query_stopwords_do_not_pull_in_every_chunk() -> None:
    index = SearchIndex(
        [
            make_record(1, "parse_file", source_code="a = 1"),
            make_record(2, "other", source_code="a = 1; the of for"),
        ]
    )
    assert names(index.search("parse a file")) == ["parse_file"]


def test_query_made_only_of_stopwords_still_searches() -> None:
    index = SearchIndex([make_record(1, "the", source_code="pass")])
    assert names(index.search("the")) == ["the"]


def test_idf_uses_the_whole_repository_not_only_matching_chunks() -> None:
    # "common" is in every chunk, "rare" in one. Whole-repository statistics
    # give "rare" far more weight, so the chunk with "rare" wins even though
    # the other chunk mentions "common" more often.
    records = [
        make_record(1, "a", source_code="common rare"),
        make_record(2, "b", source_code="common common common"),
        make_record(3, "c", source_code="common"),
        make_record(4, "d", source_code="common"),
    ]
    assert names(SearchIndex(records).search("common rare"))[0] == "a"


def test_repeating_one_term_does_not_beat_matching_two_terms() -> None:
    # BM25 saturates term frequency: a hundred mentions of "alpha" are worth
    # less than one mention each of "alpha" and "beta".
    config = replace(DEFAULT_CONFIG, stem=False, b_body=0.0, weight_body=1.0)
    records = [
        make_record(1, "many", source_code="alpha " * 100),
        make_record(2, "both", source_code="alpha beta"),
        make_record(3, "filler_one", source_code="gamma"),
        make_record(4, "filler_two", source_code="gamma"),
    ]
    assert names(SearchIndex(records, config).search("alpha beta"))[:2] == ["both", "many"]


def test_scores_match_hand_computed_bm25f() -> None:
    config = SearchConfig(
        weight_name=2.0,
        weight_path=0.0,
        weight_docstring=0.0,
        weight_body=1.0,
        b_name=0.0,
        b_body=0.0,
        k1=1.2,
        stem=False,
        split_identifiers=False,
        drop_query_stopwords=False,
        exact_symbol_first=False,
    )
    records = [
        make_record(1, "token", source_code="token token other"),
        make_record(2, "plain", source_code="other"),
    ]
    results = SearchIndex(records, config).search("token")
    assert names(results) == ["token"]

    # N = 2, n = 1 -> idf = ln(1 + (2 - 1 + 0.5) / (1 + 0.5)) = ln 2
    # tf' = 2.0 * 1 (name) + 1.0 * 2 (body) = 4, score = idf * 4 / (1.2 + 4)
    expected = math.log(2) * 4 / (1.2 + 4)
    index = SearchIndex(records, config)
    postings = dict(index._postings["token"])
    field_tf = postings[0]
    weighted = sum(w * tf for w, tf in zip(index._field_weights, field_tf, strict=False))
    assert math.isclose(index._idf["token"] * weighted / (1.2 + weighted), expected)


def test_exact_symbol_name_outranks_stronger_text_matches() -> None:
    records = [
        make_record(
            1,
            "before_request_hooks",
            path="before_request.py",
            source_code="before_request " * 30,
            docstring="before_request before_request before_request",
        ),
        make_record(2, "before_request", path="other.py"),
    ]
    assert names(SearchIndex(records).search("before_request"))[0] == "before_request"
    # Exact match is a priority rule, case-insensitive.
    assert names(SearchIndex(records).search("Before_Request"))[0] == "before_request"


def test_class_is_indexed_by_its_own_text_not_its_methods() -> None:
    class_source = (
        "class Greeter:\n"
        '    """Says hello."""\n'
        "    def run(self):\n"
        "        return needle_word\n"
    )
    records = [
        make_record(1, "Greeter", symbol_type="class", start_line=1, end_line=4,
                    docstring="Says hello.", source_code=class_source),
        make_record(2, "run", symbol_type="method", start_line=3, end_line=4,
                    source_code="def run(self):\n    return needle_word"),
    ]
    assert names(SearchIndex(records).search("needle_word")) == ["run"]

    full = replace(DEFAULT_CONFIG, class_body="full")
    assert set(names(SearchIndex(records, full).search("needle_word"))) == {"Greeter", "run"}


def test_class_summary_still_lists_method_names() -> None:
    class_source = "class Greeter:\n    def wave(self):\n        pass\n"
    records = [
        make_record(1, "Greeter", symbol_type="class", start_line=1, end_line=3,
                    source_code=class_source),
        make_record(2, "wave", symbol_type="method", start_line=2, end_line=3,
                    source_code="def wave(self):\n    pass"),
    ]
    assert "Greeter" in names(SearchIndex(records).search("wave"))


def test_equal_scores_are_ordered_by_location() -> None:
    records = [
        make_record(1, "same", path="z.py", start_line=1),
        make_record(2, "same", path="a.py", start_line=9),
        make_record(3, "same", path="a.py", start_line=2),
    ]
    ordered = SearchIndex(records).search("same")
    assert [(r.path, r.start_line) for r in ordered] == [("a.py", 2), ("a.py", 9), ("z.py", 1)]


def test_limit_truncates_results() -> None:
    records = [make_record(i, "same", start_line=i) for i in range(1, 6)]
    assert len(SearchIndex(records).search("same", limit=2)) == 2


def test_test_files_come_after_library_code_unless_the_query_mentions_tests() -> None:
    records = [
        make_record(1, "parse_header", path="tests/test_utils.py", docstring="parse a header"),
        make_record(2, "parse_header_value", path="lib/utils.py", source_code="x"),
    ]
    assert [r.path for r in SearchIndex(records).search("parse header")] == [
        "lib/utils.py",
        "tests/test_utils.py",
    ]
    assert SearchIndex(records).search("test parse header")[0].path == "tests/test_utils.py"
    off = replace(DEFAULT_CONFIG, tests_last=False)
    assert SearchIndex(records, off).search("parse header")[0].path == "tests/test_utils.py"


def test_pseudo_relevance_feedback_adds_terms_from_top_results() -> None:
    records = [
        make_record(1, "alpha_widget", source_code="gizmo gizmo gizmo"),
        make_record(2, "only_gizmo", source_code="gizmo"),
        make_record(3, "unrelated", source_code="nothing here"),
    ]
    assert "only_gizmo" not in names(SearchIndex(records).search("alpha"))
    config = replace(DEFAULT_CONFIG, prf_docs=1, prf_terms=3, prf_weight=0.5)
    assert names(SearchIndex(records, config).search("alpha"))[:2] == ["alpha_widget", "only_gizmo"]
