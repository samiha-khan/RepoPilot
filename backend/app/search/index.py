import math
from collections import Counter
from dataclasses import dataclass

from app.search.config import DEFAULT_CONFIG, SearchConfig
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
        # term -> [(document index, length-normalised tf per field)]
        self._postings: dict[str, list[tuple[int, tuple[float, ...]]]] = {}
        self._field_weights = (
            config.weight_name,
            config.weight_path,
            config.weight_docstring,
            config.weight_body,
        )
        self._idf: dict[str, float] = {}
        self._build()

    def __len__(self) -> int:
        return len(self._records)

    def search(self, query: str, limit: int | None = None) -> list[ChunkRecord]:
        config = self.config
        query_terms = set(
            tokenize(
                query,
                split_identifiers=config.split_identifiers,
                stem=config.stem,
                drop_stopwords=config.drop_query_stopwords,
            )
        )
        if not query_terms:
            # A query made only of stopwords should still return something.
            query_terms = set(
                tokenize(
                    query,
                    split_identifiers=config.split_identifiers,
                        stem=config.stem,
                )
            )

        scores: dict[int, float] = {}
        for term in query_terms:
            idf = self._idf.get(term)
            if idf is None:
                continue
            for doc_index, field_tf in self._postings[term]:
                if config.combine == "bm25f":
                    weighted_tf = sum(
                        w * tf for w, tf in zip(self._field_weights, field_tf, strict=True)
                    )
                    contribution = weighted_tf / (config.k1 + weighted_tf)
                else:
                    contribution = sum(
                        w * tf / (config.k1 + tf)
                        for w, tf in zip(self._field_weights, field_tf, strict=False)
                    )
                scores[doc_index] = scores.get(doc_index, 0.0) + idf * contribution

        exact_name = query.strip().lower() if config.exact_symbol_first else None

        # Equal scores are ordered by location so results are deterministic.
        ranked = sorted(
            scores,
            key=lambda i: (
                self._records[i].symbol_name.lower() != exact_name,
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

    def _build(self) -> None:
        config = self.config
        b_values = {
            "name": config.b_name,
            "path": config.b_path,
            "docstring": config.b_docstring,
            "body": config.b_body,
        }

        field_counts: list[dict[str, Counter[str]]] = []
        length_totals = dict.fromkeys(FIELDS, 0)
        document_frequency: Counter[str] = Counter()

        for text_by_field in self._field_texts():
            counts = {
                field: Counter(
                    tokenize(
                        text,
                        split_identifiers=config.split_identifiers,
                                stem=config.stem,
                    )
                )
                for field, text in text_by_field.items()
            }
            for field, counter in counts.items():
                length_totals[field] += sum(counter.values())
            document_frequency.update(set().union(*counts.values()))
            field_counts.append(counts)

        document_count = len(field_counts)
        average_lengths = {
            field: (length_totals[field] / document_count) or 1.0
            for field in FIELDS
        } if document_count else dict.fromkeys(FIELDS, 1.0)

        for doc_index, counts in enumerate(field_counts):
            vectors: dict[str, list[float]] = {}
            for position, field in enumerate(FIELDS):
                counter = counts[field]
                length = sum(counter.values())
                normaliser = (
                    1 - b_values[field] + b_values[field] * length / average_lengths[field]
                )
                for term, frequency in counter.items():
                    vectors.setdefault(term, [0.0] * len(FIELDS))[position] = (
                        frequency / normaliser
                    )
            for term, vector in vectors.items():
                self._postings.setdefault(term, []).append((doc_index, tuple(vector)))

        for term, containing in document_frequency.items():
            self._idf[term] = math.log(
                1 + (document_count - containing + 0.5) / (containing + 0.5)
            )

    def _field_texts(self):
        members = _methods_by_class(self._records)
        for record in self._records:
            if self.config.class_body == "summary" and record.symbol_type == "class":
                body = _class_summary(record, members.get(record.chunk_id, []))
            else:
                body = record.source_code
            yield {
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
