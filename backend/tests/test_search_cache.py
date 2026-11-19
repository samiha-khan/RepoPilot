import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models import CodeChunk, Repository, SourceFile
from app.services import repository_queries


@pytest.fixture()
def repository(db_session: Session) -> Repository:
    repository = Repository(owner="o", name="r", url="https://github.com/o/r")
    source_file = SourceFile(
        repository=repository, path="a.py", language="python", sha256="a" * 64, size=1
    )
    source_file.code_chunks = [
        CodeChunk(symbol_name="alpha_handler", symbol_type="function", start_line=1,
                  end_line=2, source_code="def alpha_handler(): pass"),
    ]
    db_session.add(repository)
    db_session.commit()
    return repository


def names(results) -> list[str]:
    return [chunk.symbol_name for _file, chunk in results]


def test_index_is_reused_until_the_stored_chunks_change(
    db_session: Session, repository: Repository
) -> None:
    first = repository_queries._get_index(
        db_session, repository, repository_queries.DEFAULT_CONFIG
    )
    again = repository_queries._get_index(
        db_session, repository, repository_queries.DEFAULT_CONFIG
    )
    assert first is again


def test_reindexing_is_picked_up_without_restarting(
    db_session: Session, repository: Repository
) -> None:
    assert names(repository_queries.search_repository_code(db_session, repository, "alpha")) == [
        "alpha_handler"
    ]

    # What DatabaseWriter does on a re-index: drop the files, insert new ones.
    repository.source_files.clear()
    db_session.flush()
    new_file = SourceFile(
        repository=repository, path="b.py", language="python", sha256="b" * 64, size=1
    )
    new_file.code_chunks = [
        CodeChunk(symbol_name="beta_handler", symbol_type="function", start_line=1,
                  end_line=2, source_code="def beta_handler(): pass"),
    ]
    db_session.add(new_file)
    db_session.commit()

    assert repository_queries.search_repository_code(db_session, repository, "alpha") == []
    assert names(repository_queries.search_repository_code(db_session, repository, "beta")) == [
        "beta_handler"
    ]


def test_cache_is_bounded(db_session: Session, repository: Repository, monkeypatch) -> None:
    monkeypatch.setattr(repository_queries, "INDEX_CACHE_SIZE", 1)
    other = Repository(owner="o", name="other", url="https://github.com/o/other")
    db_session.add(other)
    db_session.commit()

    repository_queries.search_repository_code(db_session, repository, "alpha")
    repository_queries.search_repository_code(db_session, other, "alpha")
    assert len(repository_queries._index_cache) == 1


def test_api_search_honours_limit(db_session: Session, repository: Repository) -> None:
    source_file = repository.source_files[0]
    source_file.code_chunks.extend(
        CodeChunk(symbol_name=f"alpha_{i}", symbol_type="function", start_line=10 + i,
                  end_line=10 + i, source_code="pass")
        for i in range(5)
    )
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        url = f"/repositories/{repository.id}/search"
        assert len(client.get(url, params={"q": "alpha", "limit": 3}).json()) == 3
        assert len(client.get(url, params={"q": "alpha"}).json()) == 6
        assert client.get(url, params={"q": "alpha", "limit": 0}).status_code == 422
        assert client.get(url, params={"q": "alpha", "limit": 201}).status_code == 422
    finally:
        app.dependency_overrides.clear()
