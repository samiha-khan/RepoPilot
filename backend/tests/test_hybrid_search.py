import json

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import CodeChunk
from app.services.database_writer import DatabaseWriter
from app.services.repository_queries import search_repository_code
from app.services.embeddings import embedding_text
from tests.test_api_repositories import make_code_chunk, make_repository, make_source_file
from tests.test_database_writer import make_index_result, make_indexed_file, make_chunk


class MappedEmbedder:
    """Puts the writer and the 'save the index' question in the same direction."""

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        if "save parsed symbols" in lowered or "def write(" in lowered:
            return [1.0, 0.0]
        if "databasewriteerror" in lowered:
            return [0.5, 0.5]
        return [0.0, 0.0]


def test_meaning_search_finds_code_whose_name_does_not_share_the_query_words(
    db_session: Session,
) -> None:
    repository = make_repository(db_session)
    source_file = make_source_file(db_session, repository, path="app/services/database_writer.py")
    writer = make_code_chunk(
        source_file,
        symbol_name="write",
        start_line=1,
        end_line=4,
        source_code="def write():\n    session.commit()\n",
        docstring="Persist the indexed repository.",
    )
    error = make_code_chunk(
        source_file,
        symbol_name="DatabaseWriteError",
        symbol_type="class",
        start_line=10,
        end_line=12,
        source_code="class DatabaseWriteError(RuntimeError):\n    pass\n",
        docstring=None,
    )
    embedder = MappedEmbedder()
    for chunk in (writer, error):
        chunk.embedding = json.dumps(
            embedder.embed_passages(
                [
                    embedding_text(
                        symbol_name=chunk.symbol_name,
                        symbol_type=chunk.symbol_type,
                        path=source_file.path,
                        docstring=chunk.docstring,
                        source_code=chunk.source_code,
                    )
                ]
            )[0]
        )
    db_session.add_all([writer, error])
    db_session.commit()

    hits = search_repository_code(
        db_session,
        repository,
        "save parsed symbols",
        embedder=embedder,
    )

    assert hits[0].code_chunk.symbol_name == "write"
    assert hits[0].matched_by == ["meaning"]
    assert hits[0].keyword_rank is None
    assert hits[0].meaning_rank == 1
    assert "do not appear in the name" in hits[0].why
    error_hit = next(hit for hit in hits if hit.code_chunk.symbol_name == "DatabaseWriteError")
    assert error_hit.meaning_rank == 2


def test_writer_stores_embeddings(db_session_factory: sessionmaker[Session]) -> None:
    writer = DatabaseWriter(session_factory=db_session_factory)
    repository = writer.write(
        make_index_result(make_indexed_file(chunks=(make_chunk(symbol_name="write"),))),
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
        embedder=MappedEmbedder(),
    )

    with db_session_factory() as session:
        chunk = session.scalars(select(CodeChunk)).one()

    assert repository.id
    stored = json.loads(chunk.embedding)
    assert stored == [1.0, 0.0]
