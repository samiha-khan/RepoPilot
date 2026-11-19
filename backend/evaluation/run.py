"""Search evaluation runner.

    python -m evaluation.run fetch        # check out the pinned corpora
    python -m evaluation.run hand         # hand-labelled queries, old vs new ranker
    python -m evaluation.run synthetic    # docstring queries on each corpus
    python -m evaluation.run ablate       # switch one design decision off at a time
    python -m evaluation.run tune         # grid search over field weights (dev split only)
    python -m evaluation.run prf          # pseudo-relevance feedback: tune on dev, report on all

Run from the ``backend`` directory.
"""

import argparse
import itertools
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.search import DEFAULT_CONFIG, ChunkRecord, SearchConfig, SearchIndex  # noqa: E402
from evaluation import corpora, metrics  # noqa: E402
from evaluation.legacy import LegacyRanker  # noqa: E402
from evaluation.queries import REPOPILOT_QUERIES, REQUESTS_QUERIES  # noqa: E402
from evaluation.synthetic import build_benchmark, build_identifier_benchmark  # noqa: E402

Search = Callable[[str, int], list[ChunkRecord]]
TOP_K = 10


@dataclass
class Outcome:
    ranks: list[int | None]

    @property
    def reciprocal_ranks(self) -> list[float]:
        return [metrics.reciprocal_rank(r) for r in self.ranks]


def new_ranker(records: list[ChunkRecord], config: SearchConfig = DEFAULT_CONFIG) -> Search:
    index = SearchIndex(records, config)
    return lambda query, limit: index.search(query, limit=limit)


def legacy_ranker(records: list[ChunkRecord]) -> Search:
    ranker = LegacyRanker(records)
    return lambda query, limit: ranker.search(query, limit=limit)


def labelled_match(symbol: str, path_part: str) -> Callable[[ChunkRecord], bool]:
    return lambda record: record.symbol_name == symbol and path_part in record.path


def chunk_matcher(chunk_id: int) -> Callable[[ChunkRecord], bool]:
    return lambda record: record.chunk_id == chunk_id


def rank_of(results: list[ChunkRecord], matches: Callable[[ChunkRecord], bool]) -> int | None:
    for position, record in enumerate(results[:TOP_K], start=1):
        if matches(record):
            return position
    return None


def run_hand_labelled(search: Search, queries: list[tuple[str, str, str]]) -> Outcome:
    ranks = []
    for query, symbol, path_part in queries:
        results = search(query, TOP_K)
        ranks.append(rank_of(results, labelled_match(symbol, path_part)))
    return Outcome(ranks)


def self_records() -> list[ChunkRecord]:
    return external_records("repopilot")


def external_records(name: str) -> list[ChunkRecord]:
    root = corpora.fetch(name)
    return corpora.records_from_directory(root, corpora.load_specs()[name]["scope"])


def row(label: str, outcome: Outcome) -> str:
    s = metrics.summarise(outcome.ranks)
    low, high = metrics.bootstrap_interval(outcome.reciprocal_ranks)
    return (
        f"| {label} | {s.queries} | {s.recall_at_1:.3f} | {s.recall_at_5:.3f} | "
        f"{s.recall_at_10:.3f} | {s.mrr:.3f} [{low:.3f}, {high:.3f}] | {s.ndcg_at_10:.3f} |"
    )


TABLE_HEADER = (
    "| ranker | queries | R@1 | R@5 | R@10 | MRR [95% CI] | nDCG@10 |\n"
    "|---|---|---|---|---|---|---|"
)


def command_fetch(_args) -> None:
    for name in corpora.load_specs():
        print(f"{name}: {corpora.fetch(name)}")


def command_hand(_args) -> None:
    sets = {
        "repopilot (backend/app)": (self_records(), REPOPILOT_QUERIES),
        "psf/requests (src/requests)": (external_records("requests"), REQUESTS_QUERIES),
    }
    for title, (records, queries) in sets.items():
        print(f"\n### {title}: {len(records)} chunks\n")
        print(TABLE_HEADER)
        old = run_hand_labelled(legacy_ranker(records), queries)
        new = run_hand_labelled(new_ranker(records), queries)
        print(row("previous ranker", old))
        print(row("BM25F (current)", new))
        if "-v" in sys.argv or _args.verbose:
            _print_misses(new_ranker(records), queries)


def _print_misses(search: Search, queries) -> None:
    for query, symbol, path_part in queries:
        results = search(query, TOP_K)
        rank = rank_of(results, labelled_match(symbol, path_part))
        if rank != 1:
            top = results[0].symbol_name if results else "(none)"
            print(f"  rank {rank}: {query!r} expected {symbol}, top was {top}")


def synthetic_benchmark(name: str):
    records = external_records(name)
    stripped, queries = build_benchmark(records)
    return stripped, queries


def run_synthetic(search: Search, queries: list[tuple[str, int]]) -> Outcome:
    ranks = []
    for text, chunk_id in queries:
        ranks.append(rank_of(search(text, TOP_K), chunk_matcher(chunk_id)))
    return Outcome(ranks)


def identifier_benchmark(name: str):
    records = external_records(name)
    return records, build_identifier_benchmark(records)


def command_synthetic(_args) -> None:
    for name, spec in corpora.load_specs().items():
        records, queries = synthetic_benchmark(name)
        if not queries:
            continue
        print(f"\n### {name} [{spec['split']}]: {len(records)} chunks, {len(queries)} queries\n")
        print(TABLE_HEADER)
        print(row("previous ranker", run_synthetic(legacy_ranker(records), queries)))
        print(row("BM25F (current)", run_synthetic(new_ranker(records), queries)))

        ident_records, ident_queries = identifier_benchmark(name)
        print(f"\n#### {name}: exact identifier lookup ({len(ident_queries)} queries)\n")
        print(TABLE_HEADER)
        print(row("previous ranker", run_synthetic(legacy_ranker(ident_records), ident_queries)))
        print(row("BM25F (current)", run_synthetic(new_ranker(ident_records), ident_queries)))


ABLATIONS: list[tuple[str, dict]] = [
    ("no stemming", {"stem": False}),
    ("keep query stopwords", {"drop_query_stopwords": False}),
    ("no identifier splitting", {"split_identifiers": False}),
    ("no exact-name priority", {"exact_symbol_first": False}),
    ("class indexed by full source", {"class_body": "full"}),
    ("per-field saturation (linear)", {"combine": "linear"}),
    (
        "equal field weights",
        {"weight_name": 1.0, "weight_path": 1.0, "weight_docstring": 1.0, "weight_body": 1.0},
    ),
]


def command_ablate(_args) -> None:
    """Each row turns one decision off. The delta is paired by query."""
    workloads = {}
    for name in corpora.load_specs():
        records, queries = synthetic_benchmark(name)
        if not queries:
            continue
        workloads[f"{name} (synthetic)"] = (
            records,
            lambda s, q=queries: run_synthetic(s, q),
        )
    for name in corpora.load_specs():
        records, queries = identifier_benchmark(name)
        if queries:
            workloads[f"{name} (identifier lookup)"] = (
                records,
                lambda s, q=queries: run_synthetic(s, q),
            )
    requests_records = external_records("requests")
    workloads["requests (hand-labelled)"] = (
        requests_records,
        lambda s: run_hand_labelled(s, REQUESTS_QUERIES),
    )
    self_data = self_records()
    workloads["repopilot (hand-labelled)"] = (
        self_data,
        lambda s: run_hand_labelled(s, REPOPILOT_QUERIES),
    )

    for title, (records, evaluate) in workloads.items():
        base = evaluate(new_ranker(records))
        print(f"\n### {title}\n")
        print("| variant | MRR | ΔMRR vs current [95% CI] |\n|---|---|---|")
        print(f"| current | {sum(base.reciprocal_ranks) / len(base.ranks):.3f} | |")
        previous = evaluate(legacy_ranker(records))
        _print_delta("previous ranker", previous, base)
        for label, changes in ABLATIONS:
            variant = evaluate(new_ranker(records, replace(DEFAULT_CONFIG, **changes)))
            _print_delta(label, variant, base)


def _print_delta(label: str, variant: Outcome, base: Outcome) -> None:
    mean, low, high = metrics.paired_bootstrap_difference(
        variant.reciprocal_ranks, base.reciprocal_ranks
    )
    mrr = sum(variant.reciprocal_ranks) / len(variant.ranks)
    print(f"| {label} | {mrr:.3f} | {mean:+.3f} [{low:+.3f}, {high:+.3f}] |")


WEIGHT_GRID = {
    "weight_name": [1.0, 2.0, 3.0, 5.0],
    "weight_path": [0.25, 0.5, 1.0],
    "weight_body": [0.25, 0.5, 1.0],
}


def command_tune(_args) -> None:
    """Grid search on the dev corpora only; test corpora are never touched."""
    dev = {
        name: synthetic_benchmark(name)
        for name, spec in corpora.load_specs().items()
        if spec["split"] == "dev"
    }
    results = []
    for values in itertools.product(*WEIGHT_GRID.values()):
        config = replace(DEFAULT_CONFIG, **dict(zip(WEIGHT_GRID, values, strict=False)))
        mrrs = []
        for records, queries in dev.values():
            outcome = run_synthetic(new_ranker(records, config), queries)
            mrrs.append(sum(outcome.reciprocal_ranks) / len(outcome.ranks))
        results.append((sum(mrrs) / len(mrrs), values))

    results.sort(reverse=True)
    print("dev corpora:", ", ".join(dev), "| mean MRR over corpora")
    print("| rank | " + " | ".join(WEIGHT_GRID) + " | dev MRR |")
    print("|---|" + "---|" * (len(WEIGHT_GRID) + 1))
    for position, (mrr, values) in enumerate(results[:10], start=1):
        print(f"| {position} | " + " | ".join(str(v) for v in values) + f" | {mrr:.4f} |")
    default_values = tuple(getattr(DEFAULT_CONFIG, name) for name in WEIGHT_GRID)
    default_mrr = next(mrr for mrr, values in results if values == default_values)
    print(f"\ncurrent defaults {default_values}: dev MRR {default_mrr:.4f}")
    print(f"worst grid point: {results[-1][1]} at {results[-1][0]:.4f}")


PRF_GRID = {
    "prf_docs": [3, 5, 10],
    "prf_terms": [5, 10, 20],
    "prf_weight": [0.1, 0.3, 0.5],
}


def command_prf(_args) -> None:
    """Pseudo-relevance feedback is chosen on the dev corpora, then reported everywhere."""
    dev = {
        name: synthetic_benchmark(name)
        for name, spec in corpora.load_specs().items()
        if spec["split"] == "dev"
    }

    def dev_mrr(config: SearchConfig) -> float:
        values = []
        for records, queries in dev.values():
            outcome = run_synthetic(new_ranker(records, config), queries)
            values.append(sum(outcome.reciprocal_ranks) / len(outcome.ranks))
        return sum(values) / len(values)

    baseline = dev_mrr(DEFAULT_CONFIG)
    results = []
    for values in itertools.product(*PRF_GRID.values()):
        config = replace(DEFAULT_CONFIG, **dict(zip(PRF_GRID, values, strict=True)))
        results.append((dev_mrr(config), values))
    results.sort(reverse=True)

    print(f"dev corpora: {', '.join(dev)} | mean MRR; feedback off = {baseline:.4f}\n")
    print("| rank | docs | terms | weight | dev MRR |\n|---|---|---|---|---|")
    for position, (mrr, values) in enumerate(results[:8], start=1):
        print(f"| {position} | " + " | ".join(str(v) for v in values) + f" | {mrr:.4f} |")
    print(f"\nworst grid point: {results[-1][1]} at {results[-1][0]:.4f}")

    best = replace(DEFAULT_CONFIG, **dict(zip(PRF_GRID, results[0][1], strict=True)))
    print(f"\nbest dev setting {results[0][1]} against feedback off, every corpus:\n")
    print("| workload | MRR off | MRR on | difference [95% CI] |\n|---|---|---|---|")
    for name, spec in corpora.load_specs().items():
        records, queries = synthetic_benchmark(name)
        if queries:
            _print_prf_row(
                f"{name} docstring [{spec['split']}]",
                records,
                lambda s, q=queries: run_synthetic(s, q),
                best,
            )
        records, queries = identifier_benchmark(name)
        if queries:
            _print_prf_row(
                f"{name} identifier [{spec['split']}]",
                records,
                lambda s, q=queries: run_synthetic(s, q),
                best,
            )
    _print_prf_row(
        "requests hand-labelled [test]",
        external_records("requests"),
        lambda s: run_hand_labelled(s, REQUESTS_QUERIES),
        best,
    )
    _print_prf_row(
        "repopilot hand-labelled [test]",
        self_records(),
        lambda s: run_hand_labelled(s, REPOPILOT_QUERIES),
        best,
    )


def _print_prf_row(label: str, records, evaluate, config: SearchConfig) -> None:
    off = evaluate(new_ranker(records))
    on = evaluate(new_ranker(records, config))
    mean, low, high = metrics.paired_bootstrap_difference(on.reciprocal_ranks, off.reciprocal_ranks)
    off_mrr = sum(off.reciprocal_ranks) / len(off.ranks)
    on_mrr = sum(on.reciprocal_ranks) / len(on.ranks)
    print(f"| {label} | {off_mrr:.3f} | {on_mrr:.3f} | {mean:+.3f} [{low:+.3f}, {high:+.3f}] |")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function in [
        ("fetch", command_fetch),
        ("hand", command_hand),
        ("synthetic", command_synthetic),
        ("ablate", command_ablate),
        ("tune", command_tune),
        ("prf", command_prf),
    ]:
        commands.add_parser(name).set_defaults(function=function)
    arguments = parser.parse_args()
    arguments.function(arguments)


if __name__ == "__main__":
    main()
