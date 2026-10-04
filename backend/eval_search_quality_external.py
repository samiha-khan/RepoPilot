"""Search quality evaluation on a genuinely external codebase.

docs/search-evaluation.md's own "Honest limitations" section flags that
eval_search_quality.py only measures ranking quality on RepoPilot's own
backend, which shares vocabulary with the queries (Python code about
parsing and searching Python code), and that this could make results look
better than they would on a codebase the queries weren't written by
someone who knows as well. This script closes that specific gap: it
indexes the real psf/requests library (a well-known, widely used HTTP
library with no relationship to RepoPilot) with the same real parser and
the same real search_repository_code() function, against a hand-written
query set sourced by reading requests' actual source in src/requests/
before running anything, the same way the original eval was built.

Needs a local clone of psf/requests at REQUESTS_SRC (see --help), since
indexing requires real source files, not the PyPI package.

Run from repo root:
    python backend/eval_search_quality_external.py --requests-src /path/to/requests/src/requests
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
from app.services.python_parser import parse_file
from app.services.repository_queries import search_repository_code

# (query, expected_symbol_name, expected_file_substring)
# Written by reading requests' real source (src/requests/*.py) before
# running this script, the same way the original eval's queries were
# written from RepoPilot's own source. Each expected symbol name was
# checked for uniqueness across the whole package first; where a name is
# reused (get/post/cookiejar_from_dict all appear in more than one file),
# the file substring is what disambiguates, exactly as the original eval
# does for its own "write" / DatabaseWriteError case.
QUERIES: list[tuple[str, str, str]] = [
    ("get", "get", "api.py"),
    ("send a get request", "get", "api.py"),
    ("post", "post", "api.py"),
    ("basic auth", "HTTPBasicAuth", "auth.py"),
    ("digest authentication", "HTTPDigestAuth", "auth.py"),
    ("case insensitive dictionary", "CaseInsensitiveDict", "structures.py"),
    ("ambiguous request exception", "RequestException", "exceptions.py"),
    ("connection timeout error", "ConnectTimeout", "exceptions.py"),
    ("too many redirects", "TooManyRedirects", "exceptions.py"),
    ("build a cookiejar from a dict", "cookiejar_from_dict", "cookies.py"),
    ("convert a cookiejar to a dict", "dict_from_cookiejar", "utils.py"),
    ("guess json encoding from bytes", "guess_json_utf", "utils.py"),
    ("get encoding from http headers", "get_encoding_from_headers", "utils.py"),
    ("re-quote a uri", "requote_uri", "utils.py"),
    ("should we bypass proxies for this url", "should_bypass_proxies", "utils.py"),
    ("default user agent string", "default_user_agent", "utils.py"),
    ("json decode error", "JSONDecodeError", "exceptions.py"),
    ("raise exception for http error status", "raise_for_status", "models.py"),
]


def index_external_repo(session: Session, src_dir: Path) -> Repository:
    repo = Repository(
        owner="psf", name="requests",
        url="https://github.com/psf/requests", default_branch="main",
    )
    session.add(repo)
    session.flush()

    py_files = sorted(src_dir.glob("*.py"))
    total_chunks = 0
    for path in py_files:
        try:
            chunks = parse_file(path)
        except Exception as e:
            print(f"  [skip] {path.name}: {e}")
            continue

        source_file = SourceFile(
            repository_id=repo.id, path=f"src/requests/{path.name}", language="python",
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

    session.commit()
    print(f"Indexed {len(py_files)} files, {total_chunks} code chunks from psf/requests\n")
    return repo


def evaluate(session: Session, repo: Repository) -> None:
    hits_at_1 = 0
    hits_at_3 = 0
    reciprocal_ranks = []
    failures = []

    for query, expected_symbol, expected_file_substr in QUERIES:
        results = search_repository_code(session, repo, query)
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

    n = len(QUERIES)
    print(f"\n=== Results on psf/requests (n={n} queries) ===")
    print(f"Precision@1: {hits_at_1}/{n} = {hits_at_1 / n:.1%}")
    print(f"Precision@3: {hits_at_3}/{n} = {hits_at_3 / n:.1%}")
    print(f"MRR:         {sum(reciprocal_ranks) / n:.3f}")

    if failures:
        print(f"\n=== Misses (expected result not in top 3) ===")
        for query, expected, got in failures:
            print(f"  '{query}': expected {expected}, top result was {got}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requests-src", required=True, type=Path,
        help="Path to a local checkout's src/requests directory, e.g. "
             "git clone --depth 1 https://github.com/psf/requests.git && "
             "python backend/eval_search_quality_external.py --requests-src requests/src/requests",
    )
    args = parser.parse_args()
    if not args.requests_src.is_dir():
        parser.error(f"{args.requests_src} is not a directory")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = index_external_repo(session, args.requests_src)
        evaluate(session, repo)


if __name__ == "__main__":
    main()
