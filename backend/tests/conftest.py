import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models
from app.db.base import Base

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://repofix:repofix@db:5432/repofix_test"


def get_test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def assert_test_database_url(database_url: str) -> None:
    database_name = make_url(database_url).database
    if not database_name or not database_name.endswith("_test"):
        raise RuntimeError(
            "Refusing to reset a non-test database. TEST_DATABASE_URL must end with '_test'."
        )


@pytest.fixture()
def test_engine() -> Generator[Engine, None, None]:
    database_url = get_test_database_url()
    assert_test_database_url(database_url)

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session_factory(test_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest.fixture()
def db_session(db_session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with db_session_factory() as session:
        yield session
