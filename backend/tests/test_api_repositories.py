import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models import CodeChunk, Repository, SourceFile


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def make_repository(
    db_session: Session,
    *,
    owner: str = "octocat",
    name: str = "hello-world",
    url: str | None = None,
    default_branch: str | None = "main",
) -> Repository:
    repository = Repository(
        owner=owner,
        name=name,
        url=url if url is not None else f"https://github.com/{owner}/{name}",
        default_branch=default_branch,
    )
    db_session.add(repository)
    db_session.commit()
    db_session.refresh(repository)
    return repository


def make_source_file(
    db_session: Session,
    repository: Repository,
    *,
    path: str = "src/app.py",
    sha256: str = "a" * 64,
    size: int = 128,
) -> SourceFile:
    source_file = SourceFile(
        repository=repository,
        path=path,
        language="python",
        sha256=sha256,
        size=size,
    )
    db_session.add(source_file)
    db_session.flush()
    return source_file


def make_code_chunk(
    source_file: SourceFile,
    *,
    symbol_name: str = "main",
    symbol_type: str = "function",
    start_line: int = 1,
    end_line: int = 2,
    source_code: str | None = None,
    docstring: str | None = None,
) -> CodeChunk:
    return CodeChunk(
        source_file=source_file,
        symbol_name=symbol_name,
        symbol_type=symbol_type,
        start_line=start_line,
        end_line=end_line,
        source_code=source_code
        if source_code is not None
        else f"def {symbol_name}():\n    pass\n",
        docstring=docstring,
    )


def test_list_repositories_returns_indexed_repositories(
    client: TestClient,
    db_session: Session,
) -> None:
    make_repository(db_session, owner="zeta", name="api")
    first = make_repository(
        db_session,
        owner="alpha",
        name="core",
        default_branch=None,
    )

    response = client.get("/repositories")

    assert response.status_code == 200
    data = response.json()
    assert [repository["owner"] for repository in data] == ["alpha", "zeta"]
    assert data[0] | {"created_at": None, "updated_at": None} == {
        "id": first.id,
        "owner": "alpha",
        "name": "core",
        "url": "https://github.com/alpha/core",
        "default_branch": None,
        "created_at": None,
        "updated_at": None,
    }
    assert data[0]["created_at"]
    assert data[0]["updated_at"]


def test_get_repository_returns_details(client: TestClient, db_session: Session) -> None:
    repository = make_repository(db_session)

    response = client.get(f"/repositories/{repository.id}")

    assert response.status_code == 200
    assert response.json()["id"] == repository.id
    assert response.json()["owner"] == "octocat"
    assert response.json()["name"] == "hello-world"
    assert response.json()["url"] == "https://github.com/octocat/hello-world"
    assert response.json()["default_branch"] == "main"


def test_get_repository_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/repositories/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Repository not found."}


def test_list_repository_files_returns_files_in_path_order(
    client: TestClient,
    db_session: Session,
) -> None:
    repository = make_repository(db_session)
    make_source_file(db_session, repository, path="z.py", sha256="z" * 64, size=30)
    first = make_source_file(
        db_session,
        repository,
        path="src/a.py",
        sha256="b" * 64,
        size=20,
    )
    db_session.commit()

    response = client.get(f"/repositories/{repository.id}/files")

    assert response.status_code == 200
    data = response.json()
    assert [source_file["path"] for source_file in data] == ["src/a.py", "z.py"]
    assert data[0] | {"created_at": None, "updated_at": None} == {
        "id": first.id,
        "path": "src/a.py",
        "language": "python",
        "sha256": "b" * 64,
        "size": 20,
        "created_at": None,
        "updated_at": None,
    }
    assert data[0]["created_at"]
    assert data[0]["updated_at"]


def test_list_repository_files_returns_404_when_repository_is_missing(
    client: TestClient,
) -> None:
    response = client.get("/repositories/999/files")

    assert response.status_code == 404
    assert response.json() == {"detail": "Repository not found."}


@pytest.mark.parametrize(
    "query",
    [
        "handler",
        "RETURN USER",
        "loads user data",
        "services/users.py",
    ],
)
def test_search_repository_code_matches_expected_fields(
    client: TestClient,
    db_session: Session,
    query: str,
) -> None:
    repository = make_repository(db_session)
    source_file = make_source_file(db_session, repository, path="services/users.py")
    db_session.add(
        make_code_chunk(
            source_file,
            symbol_name="UserHandler",
            start_line=4,
            end_line=8,
            source_code="def handle_user():\n    return user\n",
            docstring="Loads user data",
        )
    )
    db_session.commit()

    response = client.get(
        f"/repositories/{repository.id}/search",
        params={"q": query},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "file_path": "services/users.py",
            "symbol_name": "UserHandler",
            "symbol_type": "function",
            "start_line": 4,
            "end_line": 8,
            "docstring": "Loads user data",
            "source_code": "def handle_user():\n    return user\n",
        }
    ]


def test_search_repository_code_is_scoped_to_repository(
    client: TestClient,
    db_session: Session,
) -> None:
    target_repository = make_repository(db_session, owner="target", name="repo")
    other_repository = make_repository(db_session, owner="other", name="repo")
    target_file = make_source_file(db_session, target_repository, path="target.py")
    other_file = make_source_file(db_session, other_repository, path="other.py")
    db_session.add_all(
        [
            make_code_chunk(target_file, symbol_name="SharedName"),
            make_code_chunk(other_file, symbol_name="SharedName"),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/repositories/{target_repository.id}/search",
        params={"q": "SharedName"},
    )

    assert response.status_code == 200
    assert [result["file_path"] for result in response.json()] == ["target.py"]


def test_search_repository_code_orders_results_deterministically(
    client: TestClient,
    db_session: Session,
) -> None:
    repository = make_repository(db_session)
    z_file = make_source_file(db_session, repository, path="z.py")
    a_file = make_source_file(db_session, repository, path="a.py", sha256="b" * 64)
    db_session.add_all(
        [
            make_code_chunk(z_file, symbol_name="Alpha", start_line=1, end_line=1),
            make_code_chunk(a_file, symbol_name="Beta", start_line=5, end_line=5),
            make_code_chunk(a_file, symbol_name="Alpha", start_line=5, end_line=5),
            make_code_chunk(a_file, symbol_name="Gamma", start_line=2, end_line=2),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/repositories/{repository.id}/search",
        params={"q": "a"},
    )

    assert response.status_code == 200
    assert [
        (result["file_path"], result["start_line"], result["symbol_name"])
        for result in response.json()
    ] == [
        ("a.py", 2, "Gamma"),
        ("a.py", 5, "Alpha"),
        ("a.py", 5, "Beta"),
        ("z.py", 1, "Alpha"),
    ]


def test_search_repository_code_ranks_exact_symbol_matches_first(
    client: TestClient,
    db_session: Session,
) -> None:
    repository = make_repository(db_session)
    source_file = make_source_file(db_session, repository, path="handlers.py")
    db_session.add_all(
        [
            make_code_chunk(
                source_file,
                symbol_name="UserHandler",
                start_line=20,
                end_line=22,
                source_code="def different_name():\n    return 'UserHandler'\n",
            ),
            make_code_chunk(
                source_file,
                symbol_name="build_user_handler",
                start_line=1,
                end_line=3,
                source_code="def build_user_handler():\n    pass\n",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/repositories/{repository.id}/search",
        params={"q": "UserHandler"},
    )

    assert response.status_code == 200
    assert [result["symbol_name"] for result in response.json()] == [
        "UserHandler",
        "build_user_handler",
    ]


def test_search_repository_code_ranks_partial_symbols_over_source_only_matches(
    client: TestClient,
    db_session: Session,
) -> None:
    repository = make_repository(db_session)
    source_file = make_source_file(db_session, repository, path="workers.py")
    db_session.add_all(
        [
            make_code_chunk(
                source_file,
                symbol_name="PaymentProcessor",
                start_line=20,
                end_line=22,
                source_code="def unrelated():\n    return None\n",
            ),
            make_code_chunk(
                source_file,
                symbol_name="run_task",
                start_line=1,
                end_line=3,
                source_code="def run_task():\n    payment_processor = True\n",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/repositories/{repository.id}/search",
        params={"q": "processor"},
    )

    assert response.status_code == 200
    assert [result["symbol_name"] for result in response.json()] == [
        "PaymentProcessor",
        "run_task",
    ]


def test_search_repository_code_excludes_unrelated_chunks(
    client: TestClient,
    db_session: Session,
) -> None:
    repository = make_repository(db_session)
    source_file = make_source_file(db_session, repository, path="reports.py")
    db_session.add_all(
        [
            make_code_chunk(
                source_file,
                symbol_name="DailyReport",
                start_line=1,
                end_line=3,
                source_code="def daily_report():\n    pass\n",
            ),
            make_code_chunk(
                source_file,
                symbol_name="Archive",
                start_line=10,
                end_line=12,
                source_code="def archive():\n    pass\n",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/repositories/{repository.id}/search",
        params={"q": "daily"},
    )

    assert response.status_code == 200
    assert [result["symbol_name"] for result in response.json()] == ["DailyReport"]


def test_search_repository_code_returns_404_when_repository_is_missing(
    client: TestClient,
) -> None:
    response = client.get("/repositories/999/search", params={"q": "main"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Repository not found."}


def test_search_repository_code_requires_query(client: TestClient) -> None:
    response = client.get("/repositories/1/search")

    assert response.status_code == 422


def test_search_repository_code_rejects_empty_query(client: TestClient) -> None:
    response = client.get("/repositories/1/search", params={"q": ""})

    assert response.status_code == 422
