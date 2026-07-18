import math
import re
from collections import Counter

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import CodeChunk, Repository, SourceFile

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")

FIELD_WEIGHTS = {
    "symbol_name": 8.0,
    "file_path": 4.0,
    "docstring": 2.0,
    "source_code": 1.0,
}
EXACT_SYMBOL_MATCH_BOOST = 100.0
PARTIAL_SYMBOL_MATCH_BOOST = 25.0
BM25_K1 = 1.5
BM25_B = 0.75


def list_repositories(db: Session) -> list[Repository]:
    return list(
        db.scalars(
            select(Repository).order_by(
                Repository.owner,
                Repository.name,
                Repository.id,
            )
        )
    )


def get_repository(db: Session, repository_id: int) -> Repository | None:
    return db.get(Repository, repository_id)


def list_repository_files(db: Session, repository: Repository) -> list[SourceFile]:
    return list(
        db.scalars(
            select(SourceFile)
            .where(SourceFile.repository_id == repository.id)
            .order_by(SourceFile.path, SourceFile.id)
        )
    )


def search_repository_code(
    db: Session,
    repository: Repository,
    query: str,
) -> list[tuple[SourceFile, CodeChunk]]:
    candidates = _find_search_candidates(db, repository, query)
    corpus = _build_search_corpus(candidates)
    return [
        source_file_and_chunk
        for _score, source_file_and_chunk in sorted(
            (
                (
                    _score_search_result(
                        source_file,
                        code_chunk,
                        query,
                        corpus,
                    ),
                    (source_file, code_chunk),
                )
                for source_file, code_chunk in candidates
            ),
            key=lambda scored_result: (
                -scored_result[0],
                scored_result[1][0].path,
                scored_result[1][1].start_line,
                scored_result[1][1].symbol_name,
                scored_result[1][1].id,
            ),
        )
        if _score > 0
    ]


def _find_search_candidates(
    db: Session,
    repository: Repository,
    query: str,
) -> list[tuple[SourceFile, CodeChunk]]:
    search_terms = [query.strip(), *_tokenize(query)]
    patterns = {
        f"%{term}%"
        for term in search_terms
        if term
    }
    search_clauses = [
        or_(
            CodeChunk.symbol_name.ilike(pattern),
            CodeChunk.source_code.ilike(pattern),
            CodeChunk.docstring.ilike(pattern),
            SourceFile.path.ilike(pattern),
        )
        for pattern in patterns
    ]

    if not search_clauses:
        return []

    return list(
        db.execute(
            select(SourceFile, CodeChunk)
            .join(CodeChunk, CodeChunk.source_file_id == SourceFile.id)
            .where(SourceFile.repository_id == repository.id)
            .where(or_(*search_clauses))
        )
    )


def _score_search_result(
    source_file: SourceFile,
    code_chunk: CodeChunk,
    query: str,
    corpus: dict[str, object],
) -> float:
    normalized_query = query.strip().lower()
    query_tokens = _tokenize(query)
    if not normalized_query and not query_tokens:
        return 0.0

    score = 0.0
    normalized_symbol_name = code_chunk.symbol_name.lower()

    if normalized_symbol_name == normalized_query:
        score += EXACT_SYMBOL_MATCH_BOOST
    elif normalized_query and normalized_query in normalized_symbol_name:
        score += PARTIAL_SYMBOL_MATCH_BOOST

    fields = {
        "symbol_name": code_chunk.symbol_name,
        "file_path": source_file.path,
        "docstring": code_chunk.docstring or "",
        "source_code": code_chunk.source_code,
    }
    for field_name, value in fields.items():
        score += FIELD_WEIGHTS[field_name] * _bm25_field_score(
            _tokenize(value),
            query_tokens,
            field_name,
            corpus,
        )

    return score


def _build_search_corpus(
    candidates: list[tuple[SourceFile, CodeChunk]],
) -> dict[str, object]:
    field_lengths: dict[str, list[int]] = {field_name: [] for field_name in FIELD_WEIGHTS}
    document_frequencies: dict[str, Counter[str]] = {
        field_name: Counter() for field_name in FIELD_WEIGHTS
    }

    for source_file, code_chunk in candidates:
        fields = {
            "symbol_name": code_chunk.symbol_name,
            "file_path": source_file.path,
            "docstring": code_chunk.docstring or "",
            "source_code": code_chunk.source_code,
        }
        for field_name, value in fields.items():
            tokens = _tokenize(value)
            field_lengths[field_name].append(len(tokens))
            document_frequencies[field_name].update(set(tokens))

    average_lengths = {
        field_name: sum(lengths) / len(lengths) if lengths else 0.0
        for field_name, lengths in field_lengths.items()
    }
    return {
        "document_count": len(candidates),
        "average_lengths": average_lengths,
        "document_frequencies": document_frequencies,
    }


def _bm25_field_score(
    field_tokens: list[str],
    query_tokens: list[str],
    field_name: str,
    corpus: dict[str, object],
) -> float:
    if not field_tokens or not query_tokens:
        return 0.0

    token_counts = Counter(field_tokens)
    field_length = len(field_tokens)
    document_count = int(corpus["document_count"])
    average_lengths = corpus["average_lengths"]
    document_frequencies = corpus["document_frequencies"]
    average_length = average_lengths[field_name] or 1.0

    score = 0.0
    for token in set(query_tokens):
        frequency = token_counts[token]
        if frequency == 0:
            continue

        documents_with_term = document_frequencies[field_name][token]
        idf = math.log(1 + (document_count - documents_with_term + 0.5) / (documents_with_term + 0.5))
        denominator = frequency + BM25_K1 * (
            1 - BM25_B + BM25_B * (field_length / average_length)
        )
        score += idf * ((frequency * (BM25_K1 + 1)) / denominator)

    return score


def _tokenize(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [token.lower() for token in TOKEN_PATTERN.findall(value)]
