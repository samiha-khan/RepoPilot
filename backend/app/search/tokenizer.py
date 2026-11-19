import re
from functools import lru_cache

import snowballstemmer

# A run of identifier characters: "parse_file", "HTTPBasicAuth", "bm25".
_WORD = re.compile(r"[A-Za-z0-9_]+")
# Splits one underscore-free run at case changes. The first alternative keeps
# an acronym together when a capitalised word follows ("HTTPBasic" ->
# "HTTP", "Basic").
_SUBTOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")

# Function words only. Words such as "get", "set", "list" or "run" are
# meaningful in code and are deliberately not here.
STOPWORDS = frozenset(
    """a an the of for to in on at by with from into over and or but not
    is are was were be been being this that these those it its as if then
    do does did how what which who when where why can could should would
    i we you my our your me us there here""".split()
)

_stemmer = snowballstemmer.stemmer("english")


@lru_cache(maxsize=100_000)
def _stem(word: str) -> str:
    return _stemmer.stemWord(word)


def tokenize(
    text: str,
    *,
    split_identifiers: bool = True,
    stem: bool = True,
    drop_stopwords: bool = False,
) -> list[str]:
    tokens: list[str] = []
    for word in _WORD.findall(text):
        parts = _split_word(word, split_identifiers)

        for part in parts:
            if drop_stopwords and part in STOPWORDS:
                continue
            tokens.append(_stem(part) if stem else part)

    return tokens


def _split_word(word: str, split_identifiers: bool) -> list[str]:
    if not split_identifiers:
        return [word.lower()]

    parts: list[str] = []
    for chunk in word.split("_"):
        parts.extend(match.lower() for match in _SUBTOKEN.findall(chunk))
    return parts or [word.lower()]
