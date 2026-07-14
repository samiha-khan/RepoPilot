from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.models import CodeChunk, Repository, SourceFile
from app.services.database_writer import DatabaseWriteError, DatabaseWriter
from app.services.python_parser import ParsedCodeChunk
from app.services.repository_indexer import IndexedSourceFile, RepositoryIndexResult

def make_chunk(
    *,
    symbol_name: str = "main",
    symbol_type: str = "function",
    start_line: int = 1,
    end_line: int = 2,
) -> ParsedCodeChunk:
    return ParsedCodeChunk(
        symbol_name=symbol_name,
        symbol_type=symbol_type,
        start_line=start_line,
        end_line=end_line,
        source_code=f"def {symbol_name}():\n    pass\n",
        docstring=None,
    )


def make_index_result(
    *files: IndexedSourceFile,
    repository_path: Path = Path("/tmp/repopilot"),
) -> RepositoryIndexResult:
    return RepositoryIndexResult(
        repository_path=repository_path,
        files=tuple(files),
        total_files=len(files),
        total_chunks=sum(len(file.chunks) for file in files),
        skipped_files=0,
    )


def make_indexed_file(
    *,
    path: str = "app.py",
    sha256: str = "a" * 64,
    size: int = 24,
    chunks: tuple[ParsedCodeChunk, ...] | None = None,
) -> IndexedSourceFile:
    return IndexedSourceFile(
        path=path,
        language="python",
        sha256=sha256,
        size=size,
        chunks=chunks if chunks is not None else (make_chunk(),),
    )


def load_repository(session: Session, owner: str = "octocat", name: str = "hello-world") -> Repository:
    repository = session.scalar(
        select(Repository)
        .where(Repository.owner == owner, Repository.name == name)
        .options(
            selectinload(Repository.source_files).selectinload(SourceFile.code_chunks)
        )
    )
    assert repository is not None
    return repository


def test_writes_new_repository(db_session_factory: sessionmaker[Session]) -> None:
    writer = DatabaseWriter(session_factory=db_session_factory)
    result = make_index_result()

    repository = writer.write(
        result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
        default_branch="main",
    )

    assert repository.owner == "octocat"
    assert repository.name == "hello-world"
    assert repository.url == "https://github.com/octocat/hello-world"
    assert repository.default_branch == "main"

    with db_session_factory() as session:
        saved_repository = load_repository(session)
        assert saved_repository.owner == "octocat"


def test_writes_files_and_chunks(db_session_factory: sessionmaker[Session]) -> None:
    writer = DatabaseWriter(session_factory=db_session_factory)
    chunk = make_chunk(symbol_name="Service", symbol_type="class", start_line=3, end_line=5)
    result = make_index_result(
        make_indexed_file(
            path="src/service.py",
            sha256="b" * 64,
            size=128,
            chunks=(chunk,),
        )
    )

    writer.write(
        result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
    )

    with db_session_factory() as session:
        repository = load_repository(session)
        source_file = repository.source_files[0]
        code_chunk = source_file.code_chunks[0]

        assert source_file.path == "src/service.py"
        assert source_file.language == "python"
        assert source_file.sha256 == "b" * 64
        assert source_file.size == 128
        assert code_chunk.symbol_name == "Service"
        assert code_chunk.symbol_type == "class"
        assert code_chunk.start_line == 3
        assert code_chunk.end_line == 5
        assert code_chunk.source_code == "def Service():\n    pass\n"
        assert code_chunk.docstring is None


def test_relationships_are_correct(db_session_factory: sessionmaker[Session]) -> None:
    writer = DatabaseWriter(session_factory=db_session_factory)
    result = make_index_result(
        make_indexed_file(
            path="app.py",
            chunks=(make_chunk(symbol_name="main"), make_chunk(symbol_name="helper")),
        )
    )

    writer.write(
        result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
    )

    with db_session_factory() as session:
        repository = load_repository(session)
        source_file = repository.source_files[0]

        assert source_file.repository == repository
        assert len(source_file.code_chunks) == 2
        assert all(chunk.source_file == source_file for chunk in source_file.code_chunks)


def test_reindexing_replaces_old_files_and_chunks(
    db_session_factory: sessionmaker[Session],
) -> None:
    writer = DatabaseWriter(session_factory=db_session_factory)
    writer.write(
        make_index_result(
            make_indexed_file(path="old.py", chunks=(make_chunk(symbol_name="old"),)),
            make_indexed_file(path="same.py", chunks=(make_chunk(symbol_name="same_old"),)),
        ),
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
    )

    writer.write(
        make_index_result(
            make_indexed_file(path="same.py", chunks=(make_chunk(symbol_name="same_new"),)),
            make_indexed_file(path="new.py", chunks=(make_chunk(symbol_name="new"),)),
        ),
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
    )

    with db_session_factory() as session:
        repository = load_repository(session)
        paths = sorted(source_file.path for source_file in repository.source_files)
        chunk_names = sorted(
            chunk.symbol_name
            for source_file in repository.source_files
            for chunk in source_file.code_chunks
        )

        assert paths == ["new.py", "same.py"]
        assert chunk_names == ["new", "same_new"]
        assert session.scalar(select(func.count()).select_from(SourceFile)) == 2
        assert session.scalar(select(func.count()).select_from(CodeChunk)) == 2


def test_repository_metadata_updates(db_session_factory: sessionmaker[Session]) -> None:
    writer = DatabaseWriter(session_factory=db_session_factory)
    result = make_index_result()

    writer.write(
        result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
        default_branch="main",
    )
    writer.write(
        result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/renamed",
        default_branch="trunk",
    )

    with db_session_factory() as session:
        repository = load_repository(session)
        assert repository.url == "https://github.com/octocat/renamed"
        assert repository.default_branch == "trunk"
        assert session.scalar(select(func.count()).select_from(Repository)) == 1


def test_transaction_rollback_on_failure_preserves_previous_data(
    db_session_factory: sessionmaker[Session],
) -> None:
    writer = DatabaseWriter(session_factory=db_session_factory)
    writer.write(
        make_index_result(
            make_indexed_file(
                path="stable.py",
                sha256="c" * 64,
                chunks=(make_chunk(symbol_name="stable"),),
            )
        ),
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
        default_branch="main",
    )

    invalid_result = make_index_result(
        make_indexed_file(
            path="replacement.py",
            sha256="d" * 64,
            chunks=(make_chunk(symbol_name="broken", start_line=0, end_line=1),),
        )
    )

    with pytest.raises(DatabaseWriteError):
        writer.write(
            invalid_result,
            owner="octocat",
            name="hello-world",
            url="https://github.com/octocat/changed",
            default_branch="broken",
        )

    with db_session_factory() as session:
        repository = load_repository(session)
        assert repository.url == "https://github.com/octocat/hello-world"
        assert repository.default_branch == "main"
        assert [source_file.path for source_file in repository.source_files] == ["stable.py"]
        assert repository.source_files[0].sha256 == "c" * 64
        assert [chunk.symbol_name for chunk in repository.source_files[0].code_chunks] == [
            "stable"
        ]
        assert session.scalar(select(func.count()).select_from(SourceFile)) == 1
        assert session.scalar(select(func.count()).select_from(CodeChunk)) == 1


def test_duplicate_rows_are_not_left_behind(
    db_session_factory: sessionmaker[Session],
) -> None:
    writer = DatabaseWriter(session_factory=db_session_factory)
    result = make_index_result(make_indexed_file(path="app.py"))

    writer.write(
        result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
    )
    writer.write(
        result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
    )

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Repository)) == 1
        assert session.scalar(select(func.count()).select_from(SourceFile)) == 1
        assert session.scalar(select(func.count()).select_from(CodeChunk)) == 1


@pytest.mark.parametrize(
    ("owner", "name", "url", "message"),
    [
        ("", "repo", "https://github.com/octocat/repo", "owner"),
        ("octocat", "", "https://github.com/octocat/repo", "name"),
        ("octocat", "repo", "", "URL"),
    ],
)
def test_rejects_empty_repository_metadata(
    db_session_factory: sessionmaker[Session],
    owner: str,
    name: str,
    url: str,
    message: str,
) -> None:
    writer = DatabaseWriter(session_factory=db_session_factory)

    with pytest.raises(DatabaseWriteError, match=message):
        writer.write(make_index_result(), owner=owner, name=name, url=url)
