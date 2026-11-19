"""The ranker RepoPilot used before the BM25F rewrite, kept as a baseline.

This is the previous ``repository_queries`` scoring logic, unchanged except
that it runs over in-memory chunk records instead of SQL rows. The SQL step
selected every chunk where the whole query or any query token occurred as a
substring (case-insensitive) in the symbol name, source, docstring or path;
BM25 statistics were then computed over that candidate set only.
"""

import math
import re
from collections import Counter

from app.search import ChunkRecord

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
FIELD_WEIGHTS = {"symbol_name": 8.0, "file_path": 4.0, "docstring": 2.0, "source_code": 1.0}
EXACT_SYMBOL_MATCH_BOOST = 100.0
PARTIAL_SYMBOL_MATCH_BOOST = 25.0
BM25_K1 = 1.5
BM25_B = 0.75


def _tokenize(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [token.lower() for token in TOKEN_PATTERN.findall(value)]


def _fields(record: ChunkRecord) -> dict[str, str]:
    return {
        "symbol_name": record.symbol_name,
        "file_path": record.path,
        "docstring": record.docstring or "",
        "source_code": record.source_code,
    }


class LegacyRanker:
    def __init__(self, records: list[ChunkRecord]) -> None:
        self.records = records

    def search(self, query: str, limit: int | None = None) -> list[ChunkRecord]:
        terms = {term.lower() for term in [query.strip(), *_tokenize(query)] if term}
        candidates = [
            record
            for record in self.records
            if any(term in " \n".join(_fields(record).values()).lower() for term in terms)
        ]
        corpus = self._corpus(candidates)
        scored = [(self._score(record, query, corpus), record) for record in candidates]
        ranked = sorted(
            (item for item in scored if item[0] > 0),
            key=lambda item: (
                -item[0],
                item[1].path,
                item[1].start_line,
                item[1].symbol_name,
                item[1].chunk_id,
            ),
        )
        results = [record for _score, record in ranked]
        return results[:limit] if limit is not None else results

    def _corpus(self, candidates: list[ChunkRecord]) -> dict:
        lengths = {name: [] for name in FIELD_WEIGHTS}
        frequencies = {name: Counter() for name in FIELD_WEIGHTS}
        for record in candidates:
            for name, value in _fields(record).items():
                tokens = _tokenize(value)
                lengths[name].append(len(tokens))
                frequencies[name].update(set(tokens))
        return {
            "count": len(candidates),
            "average": {n: sum(v) / len(v) if v else 0.0 for n, v in lengths.items()},
            "frequencies": frequencies,
        }

    def _score(self, record: ChunkRecord, query: str, corpus: dict) -> float:
        normalized_query = query.strip().lower()
        query_tokens = _tokenize(query)
        if not normalized_query and not query_tokens:
            return 0.0

        score = 0.0
        name = record.symbol_name.lower()
        if name == normalized_query:
            score += EXACT_SYMBOL_MATCH_BOOST
        elif normalized_query and normalized_query in name:
            score += PARTIAL_SYMBOL_MATCH_BOOST

        for field, value in _fields(record).items():
            score += FIELD_WEIGHTS[field] * self._bm25(
                _tokenize(value), query_tokens, field, corpus
            )
        return score

    def _bm25(self, field_tokens, query_tokens, field, corpus) -> float:
        if not field_tokens or not query_tokens:
            return 0.0
        counts = Counter(field_tokens)
        average = corpus["average"][field] or 1.0
        total = 0.0
        for token in set(query_tokens):
            frequency = counts[token]
            if frequency == 0:
                continue
            containing = corpus["frequencies"][field][token]
            idf = math.log(1 + (corpus["count"] - containing + 0.5) / (containing + 0.5))
            denominator = frequency + BM25_K1 * (
                1 - BM25_B + BM25_B * (len(field_tokens) / average)
            )
            total += idf * ((frequency * (BM25_K1 + 1)) / denominator)
        return total
