"""
Compare search setups side by side on every eval query set.

Setups: BM25 alone, hybrid with two embedding models (general text and
code-trained), each with and without a cross-encoder reranker.

The psf/requests set is the check against overfitting: those queries
were written for a codebase none of the search changes were designed
around. Pass --requests-src to include it.

Run from backend/:
    pip install -r requirements-embeddings.txt
    python compare_search_modes.py
    python compare_search_modes.py --requests-src /path/to/requests/src/requests

The first run downloads the models (about 0.8 GB total).
"""

import argparse
import contextlib
import io
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eval_search_quality as internal_eval
import eval_search_quality_external as external_eval
from app.db.base import Base
from app.services.embeddings import FastEmbedEmbedder, FastEmbedReranker
from app.services.repository_queries import search_repository_code

EMBEDDING_MODELS = {
    "bge-small": "BAAI/bge-small-en-v1.5",
    "jina-code": "jinaai/jina-embeddings-v2-base-code",
}
RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


def score(session, repo, queries, mode, embedder=None, reranker=None):
    hits_at_1 = hits_at_3 = 0
    reciprocal_ranks = []
    ranks = []
    for query, expected_symbol, expected_file in queries:
        results = search_repository_code(
            session, repo, query, mode=mode, embedder=embedder, reranker=reranker,
        )
        rank = next(
            (
                index + 1
                for index, (source_file, code_chunk) in enumerate(results[:10])
                if code_chunk.symbol_name == expected_symbol and expected_file in source_file.path
            ),
            None,
        )
        hits_at_1 += rank == 1
        hits_at_3 += rank is not None and rank <= 3
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        ranks.append(rank)

    n = len(queries)
    return {
        "p1": hits_at_1 / n,
        "p3": hits_at_3 / n,
        "mrr": sum(reciprocal_ranks) / n,
        "ranks": ranks,
    }


def build_corpus(name, requests_src, embedder):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    # The index functions print progress; keep the comparison output readable.
    with contextlib.redirect_stdout(io.StringIO()):
        if name == "requests":
            repo = external_eval.index_external_repo(session, requests_src)
        else:
            repo = internal_eval.index_repopilot_backend(session)
        if embedder is not None:
            internal_eval.embed_chunks(session, repo, embedder)
            session.commit()
    return session, repo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests-src", type=Path, default=None)
    parser.add_argument(
        "--show-ranks", action="store_true",
        help="print the rank of the expected answer for every query",
    )
    args = parser.parse_args()

    query_sets = [
        ("RepoPilot original", "repopilot", internal_eval.QUERIES),
        ("RepoPilot reworded", "repopilot", internal_eval.SEMANTIC_QUERIES),
    ]
    if args.requests_src is not None:
        query_sets.append(("psf/requests", "requests", external_eval.QUERIES))

    reranker = FastEmbedReranker(RERANKER_MODEL)
    rows = []

    for corpus in sorted({corpus for _title, corpus, _queries in query_sets}):
        session, repo = build_corpus(corpus, args.requests_src, None)
        for title, set_corpus, queries in query_sets:
            if set_corpus == corpus:
                rows.append((title, "bm25", score(session, repo, queries, "bm25"), queries))
        session.close()

        for label, model_name in EMBEDDING_MODELS.items():
            embedder = FastEmbedEmbedder(model_name)
            session, repo = build_corpus(corpus, args.requests_src, embedder)
            for title, set_corpus, queries in query_sets:
                if set_corpus != corpus:
                    continue
                rows.append((title, f"hybrid {label}",
                             score(session, repo, queries, "hybrid", embedder), queries))
                rows.append((title, f"hybrid {label} + rerank",
                             score(session, repo, queries, "hybrid", embedder, reranker), queries))
            session.close()

    order = [title for title, _corpus, _queries in query_sets]
    rows.sort(key=lambda row: order.index(row[0]))

    print(f"\n{'Query set':<20} {'Setup':<26} {'P@1':>7} {'P@3':>7} {'MRR':>7}")
    print("-" * 70)
    previous_title = None
    for title, setup, result, _queries in rows:
        if previous_title is not None and title != previous_title:
            print()
        previous_title = title
        print(f"{title:<20} {setup:<26} {result['p1']:>7.1%} {result['p3']:>7.1%} {result['mrr']:>7.3f}")

    if args.show_ranks:
        for title in order:
            set_rows = [row for row in rows if row[0] == title]
            queries = set_rows[0][3]
            print(f"\n=== {title}: rank of expected answer (- means not in top 10) ===")
            print("  ".join(f"[{index}] {setup}" for index, (_t, setup, _r, _q) in enumerate(set_rows)))
            for query_index, (query, _expected, _file) in enumerate(queries):
                ranks = [row[2]["ranks"][query_index] for row in set_rows]
                print("  ".join(f"{rank or '-':>3}" for rank in ranks), f"  {query}")


if __name__ == "__main__":
    main()
