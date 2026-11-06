from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api import repositories as repositories_api
from app.db.session import get_db
from app.main import app
from app.models import CodeChunk, Repository, SourceFile
from app.services.database_writer import DatabaseWriter
from app.services.embeddings import (
    MAX_SOURCE_CHARACTERS,
    build_chunk_text,
    bytes_to_vector,
    normalize,
    vector_to_bytes,
)
from app.services.python_parser import ParsedCodeChunk
from app.services.repository_indexer import IndexedSourceFile, RepositoryIndexResult
from app.services.repository_queries import (
    _reciprocal_rank_fusion,
    search_repository_code,
)

# Words that mean roughly the same thing get the same dimension, so the fake
# embedder can stand in for a real model in tests that need meaning, not
# exact words.
CONCEPTS = {
    "config": 0,
    "settings": 0,
    "configuration": 0,
    "read": 1,
    "file": 1,
    "files": 1,
    "csv": 1,
    "user": 2,
    "save": 2,
    "session": 2,
}


class FakeEmbedder:
    def __init__(self) -> None:
        self.query_calls = 0

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._embed(text) for text in texts])

    def embed_query(self, text: str) -> np.ndarray:
        self.query_calls += 1
        return self._embed(text)

    def _embed(self, text: str) -> np.ndarray:
        vector = np.full(3, 0.01, dtype=np.float32)
        for word in text.lower().replace("_", " ").replace("/", " ").replace(".", " ").split():
            if word in CONCEPTS:
                vector[CONCEPTS[word]] += 1.0
        return normalize(vector)


def make_chunk(symbol_name: str, source_code: str, docstring: str | None = None) -> ParsedCodeChunk:
    return ParsedCodeChunk(
        symbol_name=symbol_name,
        symbol_type="function",
        start_line=1,
        end_line=source_code.count("\n") + 1,
        source_code=source_code,
        docstring=docstring,
    )


def make_index_result() -> RepositoryIndexResult:
    files = (
        IndexedSourceFile(
            path="app/config.py",
            language="python",
            sha256="a" * 64,
            size=60,
            chunks=(
                make_chunk(
                    "load_config",
                    "def load_config(path):\n    with open(path) as f:\n        return json.load(f)\n",
                ),
            ),
        ),
        IndexedSourceFile(
            path="utils/files.py",
            language="python",
            sha256="b" * 64,
            size=60,
            chunks=(
                make_chunk(
                    "read_csv_file",
                    "def read_csv_file(path):\n    return list(csv.reader(open(path)))\n",
                ),
            ),
        ),
        IndexedSourceFile(
            path="app/users.py",
            language="python",
            sha256="c" * 64,
            size=60,
            chunks=(
                make_chunk(
                    "save_user",
                    "def save_user(session, user):\n    session.add(user)\n",
                ),
            ),
        ),
    )
    return RepositoryIndexResult(
        repository_path=Path("/tmp/repopilot"),
        files=files,
        total_files=len(files),
        total_chunks=len(files),
        skipped_files=0,
    )


def write_repository(
    db_session_factory: sessionmaker[Session],
    embedder: FakeEmbedder | None,
) -> None:
    DatabaseWriter(session_factory=db_session_factory, embedder=embedder).write(
        make_index_result(),
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
    )


def load_repository(session: Session) -> Repository:
    repository = session.scalar(select(Repository).where(Repository.name == "hello-world"))
    assert repository is not None
    return repository


def symbol_names(results: list[tuple[SourceFile, CodeChunk]]) -> list[str]:
    return [code_chunk.symbol_name for _source_file, code_chunk in results]


def test_writer_stores_an_embedding_for_every_chunk(
    db_session_factory: sessionmaker[Session],
) -> None:
    write_repository(db_session_factory, FakeEmbedder())

    with db_session_factory() as session:
        chunks = list(session.scalars(select(CodeChunk)))

    assert len(chunks) == 3
    for code_chunk in chunks:
        assert code_chunk.embedding is not None
        assert bytes_to_vector(code_chunk.embedding).shape == (3,)


def test_writer_skips_embeddings_without_an_embedder(
    db_session_factory: sessionmaker[Session],
) -> None:
    write_repository(db_session_factory, None)

    with db_session_factory() as session:
        chunks = list(session.scalars(select(CodeChunk)))

    assert all(code_chunk.embedding is None for code_chunk in chunks)


def test_hybrid_search_finds_a_match_with_no_shared_words(
    db_session_factory: sessionmaker[Session],
) -> None:
    embedder = FakeEmbedder()
    write_repository(db_session_factory, embedder)

    with db_session_factory() as session:
        repository = load_repository(session)
        keyword_results = search_repository_code(session, repository, "read settings file")
        hybrid_results = search_repository_code(
            session,
            repository,
            "read settings file",
            mode="hybrid",
            embedder=embedder,
        )

    assert "load_config" not in symbol_names(keyword_results)
    assert "load_config" in symbol_names(hybrid_results)


def test_hybrid_search_keeps_exact_symbol_match_first(
    db_session_factory: sessionmaker[Session],
) -> None:
    embedder = FakeEmbedder()
    write_repository(db_session_factory, embedder)

    with db_session_factory() as session:
        repository = load_repository(session)
        results = search_repository_code(
            session,
            repository,
            "save_user",
            mode="hybrid",
            embedder=embedder,
        )

    assert symbol_names(results)[0] == "save_user"


def test_hybrid_search_falls_back_to_keywords_without_stored_embeddings(
    db_session_factory: sessionmaker[Session],
) -> None:
    embedder = FakeEmbedder()
    write_repository(db_session_factory, None)

    with db_session_factory() as session:
        repository = load_repository(session)
        keyword_results = search_repository_code(session, repository, "read csv file")
        hybrid_results = search_repository_code(
            session,
            repository,
            "read csv file",
            mode="hybrid",
            embedder=embedder,
        )

    assert symbol_names(hybrid_results) == symbol_names(keyword_results)


def test_bm25_mode_never_calls_the_embedder(
    db_session_factory: sessionmaker[Session],
) -> None:
    embedder = FakeEmbedder()
    write_repository(db_session_factory, embedder)

    with db_session_factory() as session:
        repository = load_repository(session)
        search_repository_code(session, repository, "read csv file", embedder=embedder)

    assert embedder.query_calls == 0


def test_reciprocal_rank_fusion_rewards_results_found_by_both_rankers() -> None:
    def result(chunk_id: int) -> tuple[SimpleNamespace, SimpleNamespace]:
        return SimpleNamespace(path="app.py"), SimpleNamespace(id=chunk_id)

    keyword_ranking = [result(1), result(2), result(3)]
    vector_ranking = [result(4), result(2), result(1)]

    fused = _reciprocal_rank_fusion([keyword_ranking, vector_ranking])

    assert [code_chunk.id for _file, code_chunk in fused] == [1, 2, 4, 3]


def test_vector_bytes_round_trip() -> None:
    vector = np.array([0.25, -1.5, 3.0], dtype=np.float32)

    assert np.array_equal(bytes_to_vector(vector_to_bytes(vector)), vector)


def test_chunk_text_includes_docstring_and_caps_source_length() -> None:
    text = build_chunk_text(
        symbol_name="load_config",
        file_path="app/config.py",
        docstring="Read the settings file.",
        source_code="x" * (MAX_SOURCE_CHARACTERS + 500),
    )

    assert text.startswith("load config\napp/config.py\nRead the settings file.\n")
    assert text.count("x") == MAX_SOURCE_CHARACTERS


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_search_endpoint_supports_hybrid_mode(
    client: TestClient,
    db_session: Session,
    db_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedder = FakeEmbedder()
    write_repository(db_session_factory, embedder)
    monkeypatch.setattr(repositories_api, "get_default_embedder", lambda: embedder)
    repository = load_repository(db_session)

    response = client.get(
        f"/repositories/{repository.id}/search",
        params={"q": "read settings file", "mode": "hybrid"},
    )

    assert response.status_code == 200
    assert "load_config" in [result["symbol_name"] for result in response.json()]


def test_search_endpoint_rejects_unknown_mode(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    write_repository(db_session_factory, None)

    response = client.get("/repositories/1/search", params={"q": "config", "mode": "fuzzy"})

    assert response.status_code == 422
