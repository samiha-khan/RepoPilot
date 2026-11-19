import pytest

from app.search.tokenizer import tokenize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("parse_file", ["pars", "file"]),
        ("CaseInsensitiveDict", ["case", "insensit", "dict"]),
        ("HTTPBasicAuth", ["http", "basic", "auth"]),
        ("_private_helper", ["privat", "helper"]),
        ("bm25 score", ["bm", "25", "score"]),
        ("tokenize", ["token"]),
    ],
)
def test_tokenize_splits_identifiers_at_case_changes_and_underscores(text, expected) -> None:
    assert tokenize(text) == expected


def test_tokenize_without_stemming_keeps_words_intact() -> None:
    assert tokenize("parsing parsed", stem=False) == ["parsing", "parsed"]
    assert tokenize("parsing parsed") == ["pars", "pars"]


def test_tokenize_can_leave_identifiers_whole() -> None:
    assert tokenize("parse_file", split_identifiers=False, stem=False) == ["parse_file"]


def test_tokenize_drops_stopwords_only_when_asked() -> None:
    assert tokenize("parse a file", stem=False) == ["parse", "a", "file"]
    assert tokenize("parse a file", stem=False, drop_stopwords=True) == ["parse", "file"]


def test_tokenize_keeps_code_words_that_look_like_stopwords() -> None:
    assert tokenize("get set list run", stem=False, drop_stopwords=True) == [
        "get",
        "set",
        "list",
        "run",
    ]


def test_tokenize_ignores_punctuation() -> None:
    assert tokenize("def f(x):  # note", stem=False) == ["def", "f", "x", "note"]
