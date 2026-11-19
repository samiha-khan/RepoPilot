import math

from app.search import ChunkRecord
from evaluation import metrics
from evaluation.synthetic import (
    build_benchmark,
    build_identifier_benchmark,
    first_sentence,
    strip_docstring,
)


def record(chunk_id, name, *, symbol_type="function", docstring=None, source="pass", path="lib.py"):
    return ChunkRecord(chunk_id, path, name, symbol_type, 1, 5, docstring, source)


def test_summarise_ranks() -> None:
    summary = metrics.summarise([1, 2, None, 10])
    assert summary.queries == 4
    assert summary.recall_at_1 == 0.25
    assert summary.recall_at_5 == 0.5
    assert summary.recall_at_10 == 0.75
    assert math.isclose(summary.mrr, (1 + 0.5 + 0 + 0.1) / 4)
    assert math.isclose(summary.ndcg_at_10, (1 + 1 / math.log2(3) + 0 + 1 / math.log2(11)) / 4)


def test_bootstrap_interval_is_reproducible_and_brackets_the_mean() -> None:
    values = [1.0, 0.0, 0.5, 1.0, 0.25, 0.0, 1.0, 0.5]
    low, high = metrics.bootstrap_interval(values)
    assert (low, high) == metrics.bootstrap_interval(values)
    assert low <= sum(values) / len(values) <= high


def test_paired_difference_of_identical_runs_is_zero() -> None:
    values = [1.0, 0.5, 0.0, 0.25]
    assert metrics.paired_bootstrap_difference(values, values) == (0.0, 0.0, 0.0)


def test_first_sentence_cleans_markup_and_stops_at_the_sentence_end() -> None:
    text = "Return the ``encoding`` from :class:`Headers`.\n\nLonger explanation here."
    assert first_sentence(text) == "Return the encoding from Headers"


def test_strip_docstring_removes_function_and_method_docstrings_only() -> None:
    source = (
        "class Box:\n"
        '    """Box docs."""\n'
        "    def open(self):\n"
        '        """Open the box."""\n'
        "        return 1\n"
    )
    box = record(1, "Box", symbol_type="class", docstring="Box docs.", source=source)
    stripped = strip_docstring(box)
    assert "Open the box" not in stripped.source_code
    assert "Box docs" in stripped.source_code
    assert stripped.docstring == "Box docs."

    method = strip_docstring(
        record(2, "open", symbol_type="method", docstring="Open the box.",
               source='def open(self):\n    """Open the box."""\n    return 1')
    )
    assert method.docstring is None
    assert "Open the box" not in method.source_code
    assert "return 1" in method.source_code


def test_benchmark_drops_ambiguous_short_dunder_and_test_queries() -> None:
    records = [
        record(1, "fetch_user", docstring="Fetch a user record from storage."),
        record(2, "load_a", docstring="Load the shared configuration file."),
        record(3, "load_b", docstring="Load the shared configuration file."),
        record(4, "tiny", docstring="Too short."),
        record(5, "__init__", docstring="Create the object from its parts."),
        record(6, "check", docstring="Check that things work as intended.", path="tests/test_x.py"),
    ]
    stripped, queries = build_benchmark(records)
    assert queries == [("Fetch a user record from storage", 1)]
    assert all(r.docstring is None for r in stripped if r.symbol_type == "function")


def test_identifier_benchmark_uses_unique_multi_word_names_only() -> None:
    records = [
        record(1, "parse_file"),
        record(2, "load"),
        record(3, "dup_name"),
        record(4, "dup_name"),
        record(5, "__init__"),
    ]
    assert build_identifier_benchmark(records) == [("parse_file", 1)]
