import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Summary:
    """Metrics for a set of queries that each have one relevant chunk."""

    queries: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float


def reciprocal_rank(rank: int | None) -> float:
    return 1.0 / rank if rank else 0.0


def ndcg_at_10(rank: int | None) -> float:
    # With one relevant item the ideal DCG is 1, so nDCG is just the discount.
    return 1.0 / math.log2(rank + 1) if rank and rank <= 10 else 0.0


def summarise(ranks: list[int | None]) -> Summary:
    n = len(ranks)
    if n == 0:
        return Summary(0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def recall(k: int) -> float:
        return sum(1 for r in ranks if r is not None and r <= k) / n

    return Summary(
        queries=n,
        recall_at_1=recall(1),
        recall_at_5=recall(5),
        recall_at_10=recall(10),
        mrr=sum(reciprocal_rank(r) for r in ranks) / n,
        ndcg_at_10=sum(ndcg_at_10(r) for r in ranks) / n,
    )


def bootstrap_interval(
    values: list[float],
    *,
    iterations: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for the mean of per-query values."""
    if not values:
        return (0.0, 0.0)

    rng = random.Random(seed)
    n = len(values)
    means = sorted(
        sum(values[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(iterations)
    )
    tail = (1 - confidence) / 2
    return (means[int(tail * iterations)], means[int((1 - tail) * iterations) - 1])


def paired_bootstrap_difference(
    a: list[float],
    b: list[float],
    *,
    iterations: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Mean of (a - b) over the same queries, with a bootstrap interval.

    Both lists must be in the same query order. Pairing matters: two rankers
    are compared on identical queries, so resampling the per-query difference
    removes query difficulty from the noise.
    """
    differences = [x - y for x, y in zip(a, b, strict=True)]
    low, high = bootstrap_interval(
        differences, iterations=iterations, confidence=confidence, seed=seed
    )
    return (sum(differences) / len(differences), low, high)
