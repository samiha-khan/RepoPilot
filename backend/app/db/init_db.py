from sqlalchemy.engine import Engine

import app.models
from app.db.base import Base
from app.db.session import engine


def initialize_database_schema(database_engine: Engine = engine) -> None:
    Base.metadata.create_all(database_engine)
