import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CodeChunk, Repository, SourceFile


def make_repository(owner: str = "octocat", name: str = "hello-world") -> Repository:
    return Repository(
        owner=owner,
        name=name,
        url=f"https://github.com/{owner}/{name}",
        default_branch=None,
    )


def make_source_file(repository: Repository, path: str = "app/main.py") -> SourceFile:
    return SourceFile(
        repository=repository,
        path=path,
        language="python",
        sha256="a" * 64,
        size=128,
    )


def make_code_chunk(source_file: SourceFile, symbol_name: str = "main") -> CodeChunk:
    return CodeChunk(
        source_file=source_file,
        symbol_name=symbol_name,
        symbol_type="function",
        start_line=1,
        end_line=5,
        source_code="def main():\n    return None\n",
        docstring=None,
    )


def test_repository_source_file_code_chunk_relationships(db_session: Session) -> None:
    repository = make_repository()
    source_file = make_source_file(repository)
    code_chunk = make_code_chunk(source_file)

    db_session.add(repository)
    db_session.commit()

    saved_repository = db_session.scalar(select(Repository))

    assert saved_repository is not None
    assert saved_repository.source_files == [source_file]
    assert saved_repository.source_files[0].repository == repository
    assert saved_repository.source_files[0].code_chunks == [code_chunk]
    assert saved_repository.source_files[0].code_chunks[0].source_file == source_file


def test_duplicate_repository_owner_name_is_rejected(db_session: Session) -> None:
    db_session.add(make_repository())
    db_session.commit()

    db_session.add(make_repository())

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_source_file_repository_path_is_rejected(db_session: Session) -> None:
    repository = make_repository()
    db_session.add(repository)
    db_session.flush()
    db_session.add_all(
        [
            make_source_file(repository, path="app/main.py"),
            make_source_file(repository, path="app/main.py"),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_code_chunk_identity_is_rejected(db_session: Session) -> None:
    repository = make_repository()
    source_file = make_source_file(repository)
    db_session.add_all(
        [
            make_code_chunk(source_file, symbol_name="main"),
            make_code_chunk(source_file, symbol_name="main"),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize(
    ("start_line", "end_line"),
    [
        (0, 1),
        (5, 4),
    ],
)
def test_invalid_start_end_line_constraints_are_rejected(
    db_session: Session,
    start_line: int,
    end_line: int,
) -> None:
    repository = make_repository()
    source_file = make_source_file(repository)
    code_chunk = make_code_chunk(source_file)
    code_chunk.start_line = start_line
    code_chunk.end_line = end_line
    db_session.add(code_chunk)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_repository_delete_cascades_to_source_files_and_code_chunks(
    db_session: Session,
) -> None:
    repository = make_repository()
    source_file = make_source_file(repository)
    code_chunk = make_code_chunk(source_file)
    db_session.add(code_chunk)
    db_session.commit()

    db_session.delete(repository)
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Repository)) == 0
    assert db_session.scalar(select(func.count()).select_from(SourceFile)) == 0
    assert db_session.scalar(select(func.count()).select_from(CodeChunk)) == 0
