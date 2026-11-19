import hashlib
import threading
from collections import OrderedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CodeChunk, Repository, SourceFile
from app.search import DEFAULT_CONFIG, ChunkRecord, SearchConfig, SearchIndex
from app.search.text import first_sentence, is_test_path

# Building an index tokenises every chunk of a repository, so built indexes
# are kept in memory and reused until the stored chunks change.
INDEX_CACHE_SIZE = 4
_index_cache: OrderedDict[tuple[int, SearchConfig], tuple[str, SearchIndex]] = OrderedDict()
_index_cache_lock = threading.Lock()


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
    limit: int | None = None,
    config: SearchConfig = DEFAULT_CONFIG,
) -> list[tuple[SourceFile, CodeChunk]]:
    index = _get_index(db, repository, config)
    records = index.search(query, limit=limit)
    if not records:
        return []

    rows = {
        chunk.id: (source_file, chunk)
        for source_file, chunk in db.execute(
            select(SourceFile, CodeChunk)
            .join(CodeChunk, CodeChunk.source_file_id == SourceFile.id)
            .where(CodeChunk.id.in_([record.chunk_id for record in records]))
        )
    }
    return [rows[record.chunk_id] for record in records if record.chunk_id in rows]


def clear_index_cache() -> None:
    with _index_cache_lock:
        _index_cache.clear()


def _get_index(db: Session, repository: Repository, config: SearchConfig) -> SearchIndex:
    key = (repository.id, config)
    fingerprint = _repository_fingerprint(db, repository)

    with _index_cache_lock:
        cached = _index_cache.get(key)
        if cached is not None and cached[0] == fingerprint:
            _index_cache.move_to_end(key)
            return cached[1]

    index = SearchIndex(_load_chunk_records(db, repository), config)

    with _index_cache_lock:
        _index_cache[key] = (fingerprint, index)
        _index_cache.move_to_end(key)
        while len(_index_cache) > INDEX_CACHE_SIZE:
            _index_cache.popitem(last=False)
    return index


def _repository_fingerprint(db: Session, repository: Repository) -> str:
    """Cheap summary of the stored chunks, used to detect a re-index.

    Re-indexing deletes and re-inserts every chunk, which gives them new ids
    and creation times, so any re-index changes this value. It also works
    when another process (such as the CLI) wrote to the database.
    """
    digest = hashlib.sha1()
    rows = db.execute(
        select(
            CodeChunk.id,
            CodeChunk.created_at,
            func.length(CodeChunk.source_code),
        )
        .join(SourceFile, CodeChunk.source_file_id == SourceFile.id)
        .where(SourceFile.repository_id == repository.id)
        .order_by(CodeChunk.id)
    )
    for chunk_id, created_at, source_length in rows:
        digest.update(f"{chunk_id}:{created_at}:{source_length};".encode())
    return digest.hexdigest()


def _load_chunk_records(db: Session, repository: Repository) -> list[ChunkRecord]:
    rows = db.execute(
        select(
            CodeChunk.id,
            SourceFile.path,
            CodeChunk.symbol_name,
            CodeChunk.symbol_type,
            CodeChunk.start_line,
            CodeChunk.end_line,
            CodeChunk.docstring,
            CodeChunk.source_code,
        )
        .join(SourceFile, CodeChunk.source_file_id == SourceFile.id)
        .where(SourceFile.repository_id == repository.id)
        .order_by(SourceFile.path, CodeChunk.start_line, CodeChunk.id)
    )
    return [ChunkRecord(*row) for row in rows]


def suggest_queries(db: Session, repository: Repository, limit: int = 4) -> list[str]:
    """Example searches taken from the repository's own docstrings.

    Each suggestion is the first sentence of a public function's docstring,
    so it is a real description of something in the code and will return that
    function. Candidates are spread evenly over the sorted file paths so the
    examples do not all come from one module. Nothing is random: the same
    repository always gives the same suggestions.
    """
    rows = db.execute(
        select(SourceFile.path, CodeChunk.symbol_name, CodeChunk.docstring)
        .join(CodeChunk, CodeChunk.source_file_id == SourceFile.id)
        .where(SourceFile.repository_id == repository.id)
        .where(CodeChunk.docstring.is_not(None))
        .where(CodeChunk.symbol_type.in_(["function", "async_function", "method", "async_method"]))
        .order_by(SourceFile.path, CodeChunk.start_line)
    )
    seen: set[str] = set()
    candidates: list[str] = []
    for path, symbol_name, docstring in rows:
        if symbol_name.startswith("_") or is_test_path(path):
            continue
        sentence = first_sentence(docstring)
        if not 4 <= len(sentence.split()) <= 12 or sentence.lower() in seen:
            continue
        seen.add(sentence.lower())
        candidates.append(sentence)

    if len(candidates) <= limit:
        return candidates
    step = len(candidates) / limit
    return [candidates[int(i * step)] for i in range(limit)]
