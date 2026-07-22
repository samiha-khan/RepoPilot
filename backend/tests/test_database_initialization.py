from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app import main
from app.db.init_db import initialize_database_schema
from app.models import Repository


def test_initialize_database_schema_creates_tables() -> None:
    engine = create_engine("sqlite:///:memory:")

    initialize_database_schema(engine)

    assert {"repositories", "source_files", "code_chunks"}.issubset(
        set(inspect(engine).get_table_names())
    )


def test_initialize_database_schema_keeps_existing_data() -> None:
    engine = create_engine("sqlite:///:memory:")
    initialize_database_schema(engine)

    with Session(engine) as session:
        session.add(
            Repository(
                owner="octocat",
                name="hello-world",
                url="https://github.com/octocat/hello-world",
                default_branch="main",
            )
        )
        session.commit()

    initialize_database_schema(engine)

    with Session(engine) as session:
        repositories = list(session.scalars(select(Repository)))

    assert len(repositories) == 1
    assert repositories[0].owner == "octocat"


def test_app_startup_initializes_database_schema(monkeypatch) -> None:
    calls = 0

    def initialize_database_schema_stub() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(
        main,
        "initialize_database_schema",
        initialize_database_schema_stub,
    )

    with TestClient(main.app):
        pass

    assert calls == 1
