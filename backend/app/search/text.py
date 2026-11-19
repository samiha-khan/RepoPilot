import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
_MARKUP = re.compile(r"``|`|:\w+:|\*\*")
_TEST_FILE = re.compile(
    r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$"
)


def first_sentence(docstring: str) -> str:
    """First sentence of a docstring with reStructuredText markup removed."""
    paragraph = docstring.strip().split("\n\n")[0]
    sentence = _SENTENCE_END.split(" ".join(paragraph.split()))[0]
    return _MARKUP.sub("", sentence).strip().rstrip(".")


def is_test_path(path: str) -> bool:
    return bool(_TEST_FILE.search(path))
