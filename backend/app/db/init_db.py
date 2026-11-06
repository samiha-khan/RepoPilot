from sqlalchemy import LargeBinary, inspect, text
from sqlalchemy.engine import Engine

import app.models
from app.db.base import Base
from app.db.session import engine


def initialize_database_schema(database_engine: Engine = engine) -> None:
    Base.metadata.create_all(database_engine)
    _add_missing_embedding_column(database_engine)


def _add_missing_embedding_column(database_engine: Engine) -> None:
    # create_all doesn't alter existing tables, so databases created before
    # embeddings were added need the column added by hand.
    columns = {column["name"] for column in inspect(database_engine).get_columns("code_chunks")}
    if "embedding" in columns:
        return

    column_type = LargeBinary().compile(dialect=database_engine.dialect)
    with database_engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE code_chunks ADD COLUMN embedding {column_type}"))
