from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import CodeChunk, Repository, SourceFile
from app.services.repository_indexer import RepositoryIndexResult


class DatabaseWriteError(RuntimeError):
    pass


class DatabaseWriter:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self.session_factory = session_factory

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

                    session.flush()
                    session.expunge(repository)

                return repository
        except SQLAlchemyError as exc:
            raise DatabaseWriteError("Failed to write repository index to database.") from exc

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
