import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import CodeChunk, Repository, SourceFile
from app.services.embeddings import Embedder, cosine_similarity, decode_embedding

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
MEANING_MIN_SCORE = 0.34
KEYWORD_BLEND_WEIGHT = 0.25
MEANING_BLEND_WEIGHT = 0.75


@dataclass(frozen=True)
class SearchHit:
    source_file: SourceFile
    code_chunk: CodeChunk
    keyword_rank: int | None
    meaning_rank: int | None
    why: str

    @property
    def matched_by(self) -> list[str]:
        methods: list[str] = []
        if self.keyword_rank is not None:
            methods.append("keyword")
        if self.meaning_rank is not None:
            methods.append("meaning")
        return methods


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
    *,
    embedder: Embedder | None = None,
) -> list[SearchHit]:
    keyword_scored = _keyword_scored(db, repository, query)
    meaning_scored = _meaning_scored(db, repository, query, embedder)
    return _blend_hits(query, keyword_scored, meaning_scored)


def keyword_search(
    db: Session,
    repository: Repository,
    query: str,
) -> list[tuple[SourceFile, CodeChunk]]:
    return [
        (source_file, code_chunk)
        for _score, source_file, code_chunk in _keyword_scored(db, repository, query)
    ]


def meaning_search(
    db: Session,
    repository: Repository,
    query: str,
    embedder: Embedder,
) -> list[tuple[SourceFile, CodeChunk]]:
    return [
        (source_file, code_chunk)
        for _score, source_file, code_chunk in _meaning_scored(db, repository, query, embedder)
    ]


def _keyword_scored(
    db: Session,
    repository: Repository,
    query: str,
) -> list[tuple[float, SourceFile, CodeChunk]]:
    candidates = _find_search_candidates(db, repository, query)
    corpus = _build_search_corpus(candidates)
    scored = []
    for source_file, code_chunk in candidates:
        score = _score_search_result(source_file, code_chunk, query, corpus)
        if score <= 0:
            continue
        scored.append((score, source_file, code_chunk))
    scored.sort(key=lambda item: _keyword_sort_key(item[0], item[1], item[2]))
    return scored


def _meaning_scored(
    db: Session,
    repository: Repository,
    query: str,
    embedder: Embedder | None,
) -> list[tuple[float, SourceFile, CodeChunk]]:
    if embedder is None or not query.strip():
        return []

    rows = _load_repository_chunks(db, repository)
    stored = [
        (source_file, code_chunk, vector)
        for source_file, code_chunk in rows
        if (vector := decode_embedding(code_chunk.embedding)) is not None
    ]
    if not stored:
        return []

    query_vector = embedder.embed_query(query)
    scored = [
        (cosine_similarity(query_vector, vector), source_file, code_chunk)
        for source_file, code_chunk, vector in stored
    ]
    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].path,
            item[2].start_line,
            item[2].symbol_name,
            item[2].id or 0,
        )
    )
    return [item for item in scored if item[0] >= MEANING_MIN_SCORE]


def _blend_hits(
    query: str,
    keyword_scored: list[tuple[float, SourceFile, CodeChunk]],
    meaning_scored: list[tuple[float, SourceFile, CodeChunk]],
) -> list[SearchHit]:
    keyword_by_id = {
        code_chunk.id: (rank, score, source_file, code_chunk)
        for rank, (score, source_file, code_chunk) in enumerate(keyword_scored, start=1)
    }
    meaning_by_id = {
        code_chunk.id: (rank, score, source_file, code_chunk)
        for rank, (score, source_file, code_chunk) in enumerate(meaning_scored, start=1)
    }
    max_keyword_score = max((score for score, _file, _chunk in keyword_scored), default=0.0)

    combined: dict[int, tuple[SourceFile, CodeChunk]] = {}
    for _score, source_file, code_chunk in [*keyword_scored, *meaning_scored]:
        combined[code_chunk.id] = (source_file, code_chunk)

    blended: list[tuple[tuple, SearchHit]] = []
    for chunk_id, (source_file, code_chunk) in combined.items():
        keyword_rank = keyword_by_id[chunk_id][0] if chunk_id in keyword_by_id else None
        meaning_rank = meaning_by_id[chunk_id][0] if chunk_id in meaning_by_id else None
        keyword_score = keyword_by_id[chunk_id][1] if chunk_id in keyword_by_id else 0.0
        meaning_score = meaning_by_id[chunk_id][1] if chunk_id in meaning_by_id else 0.0
        keyword_norm = keyword_score / max_keyword_score if max_keyword_score else 0.0
        exact_symbol = code_chunk.symbol_name.lower() == query.strip().lower()
        blend = KEYWORD_BLEND_WEIGHT * keyword_norm + MEANING_BLEND_WEIGHT * meaning_score
        why = _explain_hit(
            query,
            source_file,
            code_chunk,
            keyword_rank,
            meaning_rank,
        )
        hit = SearchHit(
            source_file=source_file,
            code_chunk=code_chunk,
            keyword_rank=keyword_rank,
            meaning_rank=meaning_rank,
            why=why,
        )
        blended.append(
            (
                (
                    0 if exact_symbol else 1,
                    -blend,
                    source_file.path,
                    code_chunk.start_line,
                    code_chunk.symbol_name,
                    code_chunk.id or 0,
                ),
                hit,
            )
        )

    blended.sort(key=lambda item: item[0])
    return [hit for _key, hit in blended]


def _explain_hit(
    query: str,
    source_file: SourceFile,
    code_chunk: CodeChunk,
    keyword_rank: int | None,
    meaning_rank: int | None,
) -> str:
    parts: list[str] = []
    if keyword_rank is not None:
        parts.append(f"Keyword rank {keyword_rank}")
    if meaning_rank is not None:
        parts.append(f"Meaning rank {meaning_rank}")
    sentence = " and ".join(parts) + "."
    if keyword_rank is not None and meaning_rank is not None:
        if meaning_rank < keyword_rank:
            sentence += (
                " Meaning put it higher: the code matches the question"
                " even where the names use different words."
            )
        elif keyword_rank < meaning_rank:
            sentence += (
                " Keyword put it higher: the query words appear in the name or the code."
            )
        else:
            sentence += " Keyword and meaning agree on this rank."
    elif meaning_rank is not None:
        sentence += (
            " The query words do not appear in the name."
            " Meaning search matched what the code does."
        )
    else:
        sentence += " " + _keyword_reason(source_file, code_chunk, query)
    return sentence


def _keyword_reason(source_file: SourceFile, code_chunk: CodeChunk, query: str) -> str:
    normalized_query = query.strip().lower()
    symbol_name = code_chunk.symbol_name.lower()
    if symbol_name == normalized_query:
        return "The symbol name is an exact match."
    if normalized_query and normalized_query in symbol_name:
        return "The query appears in the symbol name."
    if normalized_query and normalized_query in source_file.path.lower():
        return "The query matches the file path."
    docstring = (code_chunk.docstring or "").lower()
    if normalized_query and normalized_query in docstring:
        return "The query appears in the docstring."
    query_tokens = set(_tokenize(query))
    if query_tokens & set(_tokenize(code_chunk.symbol_name)):
        return "The query words appear in the symbol name."
    if query_tokens & set(_tokenize(source_file.path)):
        return "The query words appear in the file path."
    if query_tokens & set(_tokenize(code_chunk.docstring or "")):
        return "The query words appear in the docstring."
    return "The query words appear in the source code."


def _keyword_sort_key(
    score: float,
    source_file: SourceFile,
    code_chunk: CodeChunk,
) -> tuple:
    return (
        -score,
        source_file.path,
        code_chunk.start_line,
        code_chunk.symbol_name,
        code_chunk.id or 0,
    )


def _load_repository_chunks(
    db: Session,
    repository: Repository,
) -> list[tuple[SourceFile, CodeChunk]]:
    return list(
        db.execute(
            select(SourceFile, CodeChunk)
            .join(CodeChunk, CodeChunk.source_file_id == SourceFile.id)
            .where(SourceFile.repository_id == repository.id)
        )
    )


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
