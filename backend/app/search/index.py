import math
from collections import Counter
from dataclasses import dataclass

from app.search.config import DEFAULT_CONFIG, SearchConfig
from app.search.text import is_test_path
from app.search.tokenizer import tokenize

FIELDS = ("name", "path", "docstring", "body")
_METHOD_TYPES = {"method", "async_method"}


@dataclass(frozen=True)
class ChunkRecord:
    """The part of a stored code chunk that search needs."""

    chunk_id: int
    path: str
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int
    docstring: str | None
    source_code: str


class SearchIndex:
    """In-memory BM25F index over the code chunks of one repository.

    Every chunk is a document with four fields: symbol name, file path,
    docstring and body. Scoring follows BM25F (Robertson, Zaragoza and Taylor,
    CIKM 2004): term frequencies are length-normalised per field and combined
    with field weights *before* the saturation step, so a term that occurs in
    several fields cannot add up to more than one saturated BM25 term.

        tf'(t, d) = sum over fields f of  w_f * tf(t, f) / (1 - b_f + b_f * len_f / avglen_f)
        score(q, d) = sum over query terms t of  idf(t) * tf'(t, d) / (k1 + tf'(t, d))

    The idf uses document frequencies over the whole repository, not only the
    chunks that happen to match the query.
    """

    def __init__(self, records: list[ChunkRecord], config: SearchConfig = DEFAULT_CONFIG):
        self.config = config
        self._records = records
        self._members = _methods_by_class(records)
        # term -> [(document index, length-normalised tf per field)]
        self._postings: dict[str, list[tuple[int, tuple[float, ...]]]] = {}
        self._field_weights = (
            config.weight_name,
            config.weight_path,
            config.weight_docstring,
            config.weight_body,
        )
        self._idf: dict[str, float] = {}
        self._average_lengths: dict[str, float] = dict.fromkeys(FIELDS, 1.0)
        self._build()

    def __len__(self) -> int:
        return len(self._records)

    def search(self, query: str, limit: int | None = None) -> list[ChunkRecord]:
        config = self.config
        query_terms = self._tokens(query, drop_stopwords=config.drop_query_stopwords)
        if not query_terms:
            # A query made only of stopwords should still return something.
            query_terms = self._tokens(query)

        weights = dict.fromkeys(set(query_terms), 1.0)
        scores = self._score(weights)
        if config.prf_docs and scores:
            expansion = self._expansion_terms(scores, set(weights))
            if expansion:
                weights.update(expansion)
                scores = self._score(weights)

        exact_name = query.strip().lower() if config.exact_symbol_first else None
        tests_last = config.tests_last and "test" not in query.lower()

        # Equal scores are ordered by location so results are deterministic.
        ranked = sorted(
            scores,
            key=lambda i: (
                self._records[i].symbol_name.lower() != exact_name,
                tests_last and is_test_path(self._records[i].path),
                -scores[i],
                self._records[i].path,
                self._records[i].start_line,
                self._records[i].symbol_name,
                self._records[i].chunk_id,
            ),
        )
        if limit is not None:
            ranked = ranked[:limit]
        return [self._records[i] for i in ranked]

    def _tokens(self, text: str, *, drop_stopwords: bool = False) -> list[str]:
        return tokenize(
            text,
            split_identifiers=self.config.split_identifiers,
            stem=self.config.stem,
            drop_stopwords=drop_stopwords,
        )

    def _score(self, term_weights: dict[str, float]) -> dict[int, float]:
        config = self.config
        scores: dict[int, float] = {}
        for term, query_weight in term_weights.items():
            idf = self._idf.get(term)
            if idf is None:
                continue
            for doc_index, field_tf in self._postings[term]:
                scores[doc_index] = scores.get(doc_index, 0.0) + (
                    query_weight * idf * self._saturate(field_tf, config)
                )
        return scores

    def _saturate(self, field_tf: tuple[float, ...], config: SearchConfig) -> float:
        if config.combine == "bm25f":
            weighted_tf = sum(w * tf for w, tf in zip(self._field_weights, field_tf, strict=True))
            return weighted_tf / (config.k1 + weighted_tf)
        return sum(
            w * tf / (config.k1 + tf) for w, tf in zip(self._field_weights, field_tf, strict=True)
        )

    def _expansion_terms(self, scores: dict[int, float], query_terms: set[str]) -> dict[str, float]:
        """Pseudo-relevance feedback: add terms that the top results share.

        The best ``prf_docs`` results are assumed relevant. Each of their terms
        is scored by idf times its saturated weight in those documents, and
        the best ``prf_terms`` terms not already in the query are added with a
        weight of ``prf_weight`` times their share of the best term's score.
        This is the idea behind relevance models (Lavrenko and Croft, 2001)
        and their query-interpolated form (Abdul-Jaleel et al., 2004), in a
        simpler form without language-model probabilities.
        """
        config = self.config
        top = sorted(scores, key=lambda i: (-scores[i], i))[: config.prf_docs]
        gathered: dict[str, float] = {}
        for doc_index in top:
            for term, field_tf in self._document_vector(doc_index).items():
                if term in query_terms or term not in self._idf:
                    continue
                gathered[term] = gathered.get(term, 0.0) + self._idf[term] * self._saturate(
                    tuple(field_tf), config
                )

        best = sorted(gathered, key=lambda t: (-gathered[t], t))[: config.prf_terms]
        if not best:
            return {}
        peak = gathered[best[0]]
        return {term: config.prf_weight * gathered[term] / peak for term in best}

    def _document_vector(self, doc_index: int) -> dict[str, list[float]]:
        return self._vector(self._counts(self._records[doc_index]))

    def _counts(self, record: ChunkRecord) -> dict[str, Counter[str]]:
        return {
            field: Counter(self._tokens(text))
            for field, text in self._field_texts(record).items()
        }

    def _vector(self, counts: dict[str, Counter[str]]) -> dict[str, list[float]]:
        """Length-normalised term frequencies of one document, one value per field."""
        config = self.config
        b_values = (config.b_name, config.b_path, config.b_docstring, config.b_body)
        vectors: dict[str, list[float]] = {}
        for position, field in enumerate(FIELDS):
            counter = counts[field]
            length = sum(counter.values())
            b = b_values[position]
            normaliser = 1 - b + b * length / self._average_lengths[field]
            for term, frequency in counter.items():
                vectors.setdefault(term, [0.0] * len(FIELDS))[position] = frequency / normaliser
        return vectors

    def _build(self) -> None:
        field_counts = [self._counts(record) for record in self._records]
        document_count = len(field_counts)

        document_frequency: Counter[str] = Counter()
        length_totals = dict.fromkeys(FIELDS, 0)
        for counts in field_counts:
            document_frequency.update(set().union(*counts.values()))
            for field, counter in counts.items():
                length_totals[field] += sum(counter.values())

        if document_count:
            self._average_lengths = {
                field: (length_totals[field] / document_count) or 1.0 for field in FIELDS
            }

        for doc_index, counts in enumerate(field_counts):
            for term, vector in self._vector(counts).items():
                self._postings.setdefault(term, []).append((doc_index, tuple(vector)))

        for term, containing in document_frequency.items():
            self._idf[term] = math.log(
                1 + (document_count - containing + 0.5) / (containing + 0.5)
            )

    def _field_texts(self, record: ChunkRecord) -> dict[str, str]:
        if self.config.class_body == "summary" and record.symbol_type == "class":
            body = _class_summary(record, self._members.get(record.chunk_id, []))
        else:
            body = record.source_code
        return {
            "name": record.symbol_name,
            "path": _path_text(record.path),
            "docstring": record.docstring or "",
            "body": body,
        }


def _path_text(path: str) -> str:
    return path.removesuffix(".py")


def _methods_by_class(records: list[ChunkRecord]) -> dict[int, list[ChunkRecord]]:
    """Map each class chunk to the method chunks that lie inside it."""
    by_path: dict[str, list[ChunkRecord]] = {}
    for record in records:
        by_path.setdefault(record.path, []).append(record)

    members: dict[int, list[ChunkRecord]] = {}
    for file_records in by_path.values():
        classes = [r for r in file_records if r.symbol_type == "class"]
        methods = [r for r in file_records if r.symbol_type in _METHOD_TYPES]
        for class_record in classes:
            members[class_record.chunk_id] = [
                method
                for method in methods
                if class_record.start_line <= method.start_line
                and method.end_line <= class_record.end_line
            ]
    return members


def _class_summary(record: ChunkRecord, methods: list[ChunkRecord]) -> str:
    """Class source with the method bodies cut out, plus the method names.

    A class chunk contains the text of all its methods, and each method is
    also its own chunk. Left alone, a class would match every query that
    matches any one of its methods, and would often outrank the method that
    is actually being asked for.
    """
    lines = record.source_code.splitlines()
    removed: set[int] = set()
    for method in methods:
        first = method.start_line - record.start_line
        last = method.end_line - record.start_line
        removed.update(range(max(first, 0), last + 1))

    kept = [line for index, line in enumerate(lines) if index not in removed]
    return "\n".join([*kept, *(method.symbol_name for method in methods)])
