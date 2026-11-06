from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import CodeChunk, Repository, SourceFile
from app.services.embeddings import (
    Embedder,
    build_chunk_text,
    get_default_embedder,
    vector_to_bytes,
)
from app.services.repository_indexer import RepositoryIndexResult

_USE_DEFAULT_EMBEDDER = object()


class DatabaseWriteError(RuntimeError):
    pass


class DatabaseWriter:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        embedder: Embedder | None = _USE_DEFAULT_EMBEDDER,
    ) -> None:
        self.session_factory = session_factory
        self.embedder = get_default_embedder() if embedder is _USE_DEFAULT_EMBEDDER else embedder

    def write(
        self,
        result: RepositoryIndexResult,
        *,
        owner: str,
        name: str,
        url: str,
        default_branch: str | None = None,
    ) -> Repository:
        self._validate_repository_metadata(owner=owner, name=name, url=url)

        try:
            with self.session_factory() as session:
                with session.begin():
                    repository = self._get_or_create_repository(
                        session=session,
                        owner=owner,
                        name=name,
                        url=url,
                        default_branch=default_branch,
                    )
                    repository.url = url
                    repository.default_branch = default_branch

                    repository.source_files.clear()
                    session.flush()

                    for indexed_file in result.files:
                        source_file = SourceFile(
                            path=indexed_file.path,
                            language=indexed_file.language,
                            sha256=indexed_file.sha256,
                            size=indexed_file.size,
                        )
                        source_file.code_chunks = [
                            CodeChunk(
                                symbol_name=chunk.symbol_name,
                                symbol_type=chunk.symbol_type,
                                start_line=chunk.start_line,
                                end_line=chunk.end_line,
                                source_code=chunk.source_code,
                                docstring=chunk.docstring,
                            )
                            for chunk in indexed_file.chunks
                        ]
                        repository.source_files.append(source_file)

                    self._embed_chunks(repository)
                    session.flush()
                    session.expunge(repository)

                return repository
        except SQLAlchemyError as exc:
            raise DatabaseWriteError("Failed to write repository index to database.") from exc

    def _embed_chunks(self, repository: Repository) -> None:
        if self.embedder is None:
            return

        chunks = [
            (source_file.path, code_chunk)
            for source_file in repository.source_files
            for code_chunk in source_file.code_chunks
        ]
        if not chunks:
            return

        vectors = self.embedder.embed_documents(
            [
                build_chunk_text(
                    symbol_name=code_chunk.symbol_name,
                    file_path=path,
                    docstring=code_chunk.docstring,
                    source_code=code_chunk.source_code,
                )
                for path, code_chunk in chunks
            ]
        )
        for (_path, code_chunk), vector in zip(chunks, vectors):
            code_chunk.embedding = vector_to_bytes(vector)

    def _get_or_create_repository(
        self,
        *,
        session: Session,
        owner: str,
        name: str,
        url: str,
        default_branch: str | None,
    ) -> Repository:
        repository = session.scalar(
            select(Repository).where(
                Repository.owner == owner,
                Repository.name == name,
            )
        )
        if repository is not None:
            return repository

        repository = Repository(
            owner=owner,
            name=name,
            url=url,
            default_branch=default_branch,
        )
        session.add(repository)
        return repository

    def _validate_repository_metadata(self, *, owner: str, name: str, url: str) -> None:
        if not owner.strip():
            raise DatabaseWriteError("Repository owner cannot be empty.")
        if not name.strip():
            raise DatabaseWriteError("Repository name cannot be empty.")
        if not url.strip():
            raise DatabaseWriteError("Repository URL cannot be empty.")
