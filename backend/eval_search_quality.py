"""
Search quality evaluation for RepoPilot.

Indexes RepoPilot's own backend (app/) using the real parser and the real
database models (in-memory SQLite instead of Postgres, purely so this can
run without a running database), then runs a hand-labeled query set
through the actual search_repository_code() function used in production.

Every expected answer below was written by reading the real source in
app/services/ and app/models/ before running this, not reverse-engineered
from whatever the ranker happened to return.

Metrics reported:
  - Precision@1: is the single top result the expected one?
  - Precision@3: is the expected result anywhere in the top 3?
  - MRR: reciprocal rank of the expected result (0 if not found in top 10)
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import CodeChunk, Repository, SourceFile
from app.services.embeddings import embedding_text, encode_embedding, get_embedder
from app.services.python_parser import parse_file
from app.services.repository_queries import keyword_search, meaning_search, search_repository_code

APP_DIR = BACKEND_ROOT / "app"

# (query, expected_symbol_name, expected_file_substring)
# Written by hand from reading the actual code before running any search.
QUERIES: list[tuple[str, str, str]] = [
    ("parse_file", "parse_file", "python_parser.py"),
    ("parse a python file", "parse_file", "python_parser.py"),
    ("bm25 field score", "_bm25_field_score", "repository_queries.py"),
    ("compute bm25 score for a field", "_bm25_field_score", "repository_queries.py"),
    ("tokenize", "_tokenize", "repository_queries.py"),
    ("search repository code", "search_repository_code", "repository_queries.py"),
    ("list repositories", "list_repositories", "repository_queries.py"),
    ("get repository by id", "get_repository", "repository_queries.py"),
    ("build search corpus", "_build_search_corpus", "repository_queries.py"),
    ("parse class methods", "_parse_class_methods", "python_parser.py"),
    ("python parse error", "PythonParseError", "python_parser.py"),
    ("parsed code chunk dataclass", "ParsedCodeChunk", "python_parser.py"),
    ("get source code for a node", "_get_source_code", "python_parser.py"),
    ("app config settings", "Settings", "config.py"),
    ("index repository from cli", "index", "cli.py"),
    ("write repository index to database", "write", "database_writer.py"),
    ("find search candidates", "_find_search_candidates", "repository_queries.py"),
    ("list files in a repository", "list_repository_files", "repository_queries.py"),
    # The words in these questions do not appear in the symbol name.
    # Expected symbols were chosen by reading the implementation.
    ("save parsed symbols into the database", "write", "database_writer.py"),
    ("break a camel case name into separate words", "_tokenize", "repository_queries.py"),
    ("how rare a word is across the indexed code", "_bm25_field_score", "repository_queries.py"),
    ("turn a github zip archive into files on disk", "_extract_repository_archive", "public_repository_indexer.py"),
]


def index_repopilot_backend(session: Session) -> Repository:
    repo = Repository(
        owner="samiha-khan", name="RepoPilot",
        url="https://github.com/samiha-khan/RepoPilot", default_branch="main",
    )
    session.add(repo)
    session.flush()

    py_files = sorted(APP_DIR.rglob("*.py"))
    total_chunks = 0
    for path in py_files:
        try:
            chunks = parse_file(path)
        except Exception as e:
            print(f"  [skip] {path.relative_to(BACKEND_ROOT)}: {e}")
            continue

        rel_path = str(path.relative_to(BACKEND_ROOT))
        source_file = SourceFile(
            repository_id=repo.id, path=rel_path, language="python",
            sha256="eval-harness", size=path.stat().st_size,
        )
        session.add(source_file)
        session.flush()

        for chunk in chunks:
            session.add(CodeChunk(
                source_file_id=source_file.id,
                symbol_name=chunk.symbol_name, symbol_type=chunk.symbol_type,
                start_line=chunk.start_line, end_line=chunk.end_line,
                source_code=chunk.source_code, docstring=chunk.docstring,
            ))
            total_chunks += 1

    session.flush()
    rows = list(
        session.execute(
            select(SourceFile, CodeChunk).join(CodeChunk, CodeChunk.source_file_id == SourceFile.id)
        )
    )
    embedder = get_embedder()
    vectors = embedder.embed_passages(
        [
            embedding_text(
                symbol_name=code_chunk.symbol_name,
                symbol_type=code_chunk.symbol_type,
                path=source_file.path,
                docstring=code_chunk.docstring,
                source_code=code_chunk.source_code,
            )
            for source_file, code_chunk in rows
        ]
    )
    for (source_file, code_chunk), vector in zip(rows, vectors):
        code_chunk.embedding = encode_embedding(vector)

    session.commit()
    print(f"Indexed {len(py_files)} files, {total_chunks} code chunks\n")
    return repo


def _rank(results, expected_symbol: str, expected_file_substr: str) -> int | None:
    for index, (source_file, code_chunk) in enumerate(results[:10]):
        if (
            code_chunk.symbol_name == expected_symbol
            and expected_file_substr in source_file.path
        ):
            return index + 1
    return None


def _print_method(name: str, session: Session, repo: Repository, search) -> None:
    hits_at_1 = 0
    hits_at_3 = 0
    reciprocal_ranks = []
    print(f"\n=== {name} ===")
    for query, expected_symbol, expected_file_substr in QUERIES:
        results = search(query)
        rank = _rank(results, expected_symbol, expected_file_substr)
        if rank == 1:
            hits_at_1 += 1
        if rank is not None and rank <= 3:
            hits_at_3 += 1
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        top_result = (
            f"{results[0][1].symbol_name} ({results[0][0].path})" if results else "(no results)"
        )
        status = "OK  " if rank == 1 else ("~   " if rank and rank <= 3 else "MISS")
        print(
            f"[{status}] '{query}' -> expected {expected_symbol}, "
            f"got #{rank if rank else '>10'}: {top_result}"
        )

    n = len(QUERIES)
    print(f"Precision@1: {hits_at_1}/{n} = {hits_at_1 / n:.1%}")
    print(f"Precision@3: {hits_at_3}/{n} = {hits_at_3 / n:.1%}")
    print(f"MRR:         {sum(reciprocal_ranks) / n:.3f}")


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = index_repopilot_backend(session)
        evaluate(session, repo)


def evaluate(session: Session, repo: Repository) -> None:
    embedder = get_embedder()
    _print_method(
        "Keyword",
        session,
        repo,
        lambda query: keyword_search(session, repo, query),
    )
    _print_method(
        "Meaning",
        session,
        repo,
        lambda query: meaning_search(session, repo, query, embedder),
    )
    _print_method(
        "Blended",
        session,
        repo,
        lambda query: [
            (hit.source_file, hit.code_chunk)
            for hit in search_repository_code(session, repo, query, embedder=embedder)
        ],
    )


if __name__ == "__main__":
    main()
