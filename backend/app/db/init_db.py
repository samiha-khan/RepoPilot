from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

import app.models
from app.db.base import Base
from app.db.session import engine


def initialize_database_schema(database_engine: Engine = engine) -> None:
    Base.metadata.create_all(database_engine)
    _ensure_embedding_column(database_engine)


def _ensure_embedding_column(database_engine: Engine) -> None:
    inspector = inspect(database_engine)
    if "code_chunks" not in inspector.get_table_names():
        return
    column_names = {column["name"] for column in inspector.get_columns("code_chunks")}
    if "embedding" in column_names:
        return
    with database_engine.begin() as connection:
        connection.execute(text("ALTER TABLE code_chunks ADD COLUMN embedding TEXT"))
