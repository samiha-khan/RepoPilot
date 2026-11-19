from sqlalchemy.engine import Engine

import app.models  # noqa: F401  (registers the tables on Base.metadata)
from app.db.base import Base
from app.db.session import engine


def initialize_database_schema(database_engine: Engine = engine) -> None:
    Base.metadata.create_all(database_engine)
