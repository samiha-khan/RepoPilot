"""
Search quality evaluation for RepoPilot.

Indexes RepoPilot's own backend (app/) using the real parser and the real
database models (in-memory SQLite instead of Postgres, purely so this can
run without a running database), then runs a hand-labeled query set
through the actual search_repository_code() function used in production.

Every expected answer below was written by reading the real source in
app/services/ and app/models/ before running this, not reverse-engineered
from whatever the ranker happened to return.

Run with --mode hybrid to compare BM25 alone against BM25 plus embeddings.
Hybrid mode downloads the embedding model the first time, so it needs
fastembed installed (pip install -r requirements-embeddings.txt).

Metrics reported:
  - Precision@1: is the single top result the expected one?
  - Precision@3: is the expected result anywhere in the top 3?
  - MRR: reciprocal rank of the expected result (0 if not found in top 10)
"""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import CodeChunk, Repository, SourceFile
from app.services.embeddings import FastEmbedEmbedder, build_chunk_text, vector_to_bytes
from app.services.python_parser import parse_file
from app.services.repository_queries import search_repository_code

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
]

# Queries worded the way someone might describe the code without knowing its
# names. Same rule as above: each expected answer came from reading the code.
SEMANTIC_QUERIES: list[tuple[str, str, str]] = [
    ("prevent path traversal when unpacking an archive", "_validate_archive_member",
     "public_repository_indexer.py"),
    ("download a repo snapshot over http", "_download_repository_archive",
     "public_repository_indexer.py"),
    ("skip node_modules and virtualenv folders", "_is_excluded", "repository_indexer.py"),
    ("make sure a path stays within the project root", "_is_inside_repository",
     "repository_indexer.py"),
    ("git clone a remote project into a temp dir", "_clone_github_repository",
     "repository_loader.py"),
    ("open and close a db connection per request", "get_db", "session.py"),
    ("line number where a decorated function begins", "_get_start_line", "python_parser.py"),
    ("turn blank strings into none", "_clean_metadata_value", "cli.py"),
    ("fix heroku postgres connection string", "normalize_database_url", "config.py"),
    ("which frontend domains can call the api", "allowed_cors_origins", "config.py"),
    ("liveness check endpoint", "health", "main.py"),
    ("combine keyword and vector rankings", "_reciprocal_rank_fusion",
     "repository_queries.py"),
]


def index_repopilot_backend(
    session: Session,
    embedder: FastEmbedEmbedder | None = None,
) -> Repository:
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

    if embedder is not None:
        embed_chunks(session, repo, embedder)

    session.commit()
    print(f"Indexed {len(py_files)} files, {total_chunks} code chunks\n")
    return repo


def embed_chunks(session: Session, repo: Repository, embedder: FastEmbedEmbedder) -> None:
    session.flush()
    rows = list(
        session.query(SourceFile, CodeChunk)
        .join(CodeChunk, CodeChunk.source_file_id == SourceFile.id)
        .filter(SourceFile.repository_id == repo.id)
    )
    vectors = embedder.embed_documents([
        build_chunk_text(
            symbol_name=chunk.symbol_name, file_path=source_file.path,
            docstring=chunk.docstring, source_code=chunk.source_code,
        )
        for source_file, chunk in rows
    ])
    for (_source_file, chunk), vector in zip(rows, vectors):
        chunk.embedding = vector_to_bytes(vector)


def evaluate(
    session: Session,
    repo: Repository,
    queries: list[tuple[str, str, str]],
    title: str,
    mode: str,
    embedder: FastEmbedEmbedder | None,
) -> None:
    print(f"=== {title} ({mode}) ===")
    hits_at_1 = 0
    hits_at_3 = 0
    reciprocal_ranks = []
    failures = []

    for query, expected_symbol, expected_file_substr in queries:
        results = search_repository_code(session, repo, query, mode=mode, embedder=embedder)
        rank = None
        for i, (source_file, code_chunk) in enumerate(results[:10]):
            if (code_chunk.symbol_name == expected_symbol
                    and expected_file_substr in source_file.path):
                rank = i + 1
                break

        if rank == 1:
            hits_at_1 += 1
        if rank is not None and rank <= 3:
            hits_at_3 += 1
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)

        top_result = (
            f"{results[0][1].symbol_name} ({results[0][0].path})" if results else "(no results)"
        )
        status = "OK  " if rank == 1 else ("~   " if rank and rank <= 3 else "MISS")
        print(f"[{status}] '{query}' -> expected {expected_symbol}, "
              f"got #{rank if rank else '>10'}: {top_result}")

        if rank is None or rank > 3:
            failures.append((query, expected_symbol, top_result))

    n = len(queries)
    print(f"\n--- Results (n={n} queries) ---")
    print(f"Precision@1: {hits_at_1}/{n} = {hits_at_1 / n:.1%}")
    print(f"Precision@3: {hits_at_3}/{n} = {hits_at_3 / n:.1%}")
    print(f"MRR:         {sum(reciprocal_ranks) / n:.3f}")

    if failures:
        print(f"\n=== Misses (expected result not in top 3) ===")
        for query, expected, got in failures:
            print(f"  '{query}': expected {expected}, top result was {got}")


    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["bm25", "hybrid"], default="bm25")
    args = parser.parse_args()

    embedder = FastEmbedEmbedder() if args.mode == "hybrid" else None
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = index_repopilot_backend(session, embedder)
        evaluate(session, repo, QUERIES, "Original queries", args.mode, embedder)
        evaluate(session, repo, SEMANTIC_QUERIES, "Differently worded queries", args.mode, embedder)


if __name__ == "__main__":
    main()
