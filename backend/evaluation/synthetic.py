"""Docstring-to-function queries, in the style of CodeSearchNet.

CodeSearchNet (Husain et al., 2019) builds large retrieval sets by using the
first sentence of a function's docstring as the query and the function as the
relevant result. That avoids a query author who has read the code, and gives
hundreds of queries per repository.

The catch is leakage: the docstring is itself part of the indexed text. Here
the docstring is removed from the indexed chunk (both the docstring field and
the literal inside the source) before ranking, so the ranker only sees the
function's name, path and code.

Queries whose text is shared by more than one function are dropped, since
there would be no single correct answer.
"""

import ast
import textwrap
from collections import Counter

from app.search import ChunkRecord
from app.search.text import first_sentence
from app.search.tokenizer import tokenize

_FUNCTION_TYPES = {"function", "async_function", "method", "async_method"}
_MIN_QUERY_WORDS = 4


def strip_docstring(record: ChunkRecord) -> ChunkRecord:
    """Remove function and method docstrings from a chunk.

    Every function docstring inside the chunk is cut out of the source, so a
    class chunk cannot leak the docstrings of its methods. The docstring
    field is cleared for function chunks. Class docstrings are kept: they are
    not used as queries.
    """
    source = record.source_code
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        tree = None

    if tree is not None:
        doomed: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                doomed.update(range(first.lineno - 1, first.end_lineno))
        lines = source.splitlines()
        source = "\n".join(line for i, line in enumerate(lines) if i not in doomed)

    return ChunkRecord(
        chunk_id=record.chunk_id,
        path=record.path,
        symbol_name=record.symbol_name,
        symbol_type=record.symbol_type,
        start_line=record.start_line,
        end_line=record.end_line,
        docstring=None if record.symbol_type in _FUNCTION_TYPES else record.docstring,
        source_code=source,
    )


def build_benchmark(
    records: list[ChunkRecord],
) -> tuple[list[ChunkRecord], list[tuple[str, int]]]:
    """Return (records with docstrings removed, [(query, relevant chunk_id)])."""
    candidates = [
        (first_sentence(record.docstring), record.chunk_id)
        for record in records
        if record.symbol_type in _FUNCTION_TYPES
        and record.docstring
        and not record.symbol_name.startswith("__")
        and "test" not in record.path.lower()
    ]
    candidates = [
        (text, chunk_id) for text, chunk_id in candidates
        if len(text.split()) >= _MIN_QUERY_WORDS
    ]
    counts = Counter(text.lower() for text, _ in candidates)
    queries = [(text, chunk_id) for text, chunk_id in candidates if counts[text.lower()] == 1]

    stripped = [strip_docstring(record) for record in records]
    return stripped, queries


def build_identifier_benchmark(records: list[ChunkRecord]) -> list[tuple[str, int]]:
    """Queries that are an exact symbol name, as a user would type to find it.

    Only names that occur once in the corpus are used, and only names that
    split into more than one word (``parse_file``, ``CaseInsensitiveDict``),
    since a one-word name cannot show whether the whole identifier matters.
    """
    counts = Counter(record.symbol_name for record in records)
    return [
        (record.symbol_name, record.chunk_id)
        for record in records
        if counts[record.symbol_name] == 1
        and not record.symbol_name.startswith("__")
        and len(tokenize(record.symbol_name, stem=False)) > 1
    ]
