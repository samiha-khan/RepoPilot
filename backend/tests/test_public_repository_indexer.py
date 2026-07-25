import io
import subprocess
import sys
import zipfile
from urllib.error import HTTPError

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Repository, SourceFile
from app.services.database_writer import DatabaseWriter
from app.services.public_repository_indexer import (
    InvalidPublicRepositoryUrlError,
    RepositoryArchiveNotFoundError,
    RepositoryArchiveTooLargeError,
    index_public_github_repository,
    parse_public_github_repository_url,
)


class FakeArchiveResponse:
    def __init__(self, content: bytes, content_length: int | None = None) -> None:
        self.content = io.BytesIO(content)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self) -> "FakeArchiveResponse":
        return self

    def __exit__(self, *args) -> None:
        self.content.close()

    def read(self, size: int = -1) -> bytes:
        return self.content.read(size)


def make_archive(files: dict[str, str]) -> bytes:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return archive_buffer.getvalue()


def test_public_repository_indexer_import_does_not_import_git_loader() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import app.services.public_repository_indexer; "
                "print('app.services.repository_loader' in sys.modules)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_parse_public_github_repository_url_accepts_normal_github_url() -> None:
    metadata = parse_public_github_repository_url(
        "https://github.com/octocat/hello-world",
    )

    assert metadata.owner == "octocat"
    assert metadata.name == "hello-world"
    assert metadata.url == "https://github.com/octocat/hello-world"


@pytest.mark.parametrize(
    "repository_url",
    [
        "http://github.com/octocat/hello-world",
        "https://example.com/octocat/hello-world",
        "https://github.com/octocat",
        "https://github.com/octocat/hello-world/issues",
        "https://github.com/octocat/hello-world?tab=readme",
    ],
)
def test_parse_public_github_repository_url_rejects_invalid_urls(
    repository_url: str,
) -> None:
    with pytest.raises(InvalidPublicRepositoryUrlError):
        parse_public_github_repository_url(repository_url)


def test_index_public_github_repository_downloads_archive_and_persists_python_code(
    monkeypatch,
    db_session_factory: sessionmaker[Session],
) -> None:
    archive_content = make_archive(
        {
            "owner-repo-abc123/README.md": "# Demo\n",
            "owner-repo-abc123/package/module.py": (
                "def run_demo():\n"
                '    """Run the demo."""\n'
                "    return True\n"
            ),
        }
    )

    def fake_urlopen(request, timeout):
        assert request.full_url == "https://api.github.com/repos/octocat/demo/zipball"
        assert request.headers["User-agent"] == "RepoPilot"
        assert timeout == 30
        return FakeArchiveResponse(archive_content)

    monkeypatch.setattr(
        "app.services.public_repository_indexer.urlopen",
        fake_urlopen,
    )

    summary = index_public_github_repository(
        "https://github.com/octocat/demo",
        writer=DatabaseWriter(session_factory=db_session_factory),
    )

    assert summary.total_files == 1
    assert summary.total_chunks == 1
    assert summary.skipped_files == 0
    assert summary.repository.owner == "octocat"
    assert summary.repository.name == "demo"

    with db_session_factory() as session:
        repository = session.scalar(
            select(Repository).where(
                Repository.owner == "octocat",
                Repository.name == "demo",
            )
        )
        assert repository is not None
        assert repository.url == "https://github.com/octocat/demo"
        assert [source_file.path for source_file in repository.source_files] == [
            "package/module.py"
        ]
        assert repository.source_files[0].code_chunks[0].symbol_name == "run_demo"


def test_index_public_github_repository_refreshes_existing_repository_data(
    monkeypatch,
    db_session_factory: sessionmaker[Session],
) -> None:
    archives = [
        make_archive(
            {
                "owner-repo-abc123/old.py": "def old_name():\n    return True\n",
            }
        ),
        make_archive(
            {
                "owner-repo-def456/new.py": "def new_name():\n    return True\n",
            }
        ),
    ]

    def fake_urlopen(request, timeout):
        return FakeArchiveResponse(archives.pop(0))

    monkeypatch.setattr(
        "app.services.public_repository_indexer.urlopen",
        fake_urlopen,
    )
    writer = DatabaseWriter(session_factory=db_session_factory)

    first = index_public_github_repository(
        "https://github.com/octocat/demo",
        writer=writer,
    )
    second = index_public_github_repository(
        "https://github.com/octocat/demo",
        writer=writer,
    )

    assert second.repository.id == first.repository.id
    with db_session_factory() as session:
        repositories = list(session.scalars(select(Repository)))
        source_files = list(session.scalars(select(SourceFile)))

    assert len(repositories) == 1
    assert [source_file.path for source_file in source_files] == ["new.py"]


def test_index_public_github_repository_rejects_oversized_archives(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeArchiveResponse(b"", content_length=25 * 1024 * 1024 + 1)

    monkeypatch.setattr(
        "app.services.public_repository_indexer.urlopen",
        fake_urlopen,
    )

    with pytest.raises(RepositoryArchiveTooLargeError):
        index_public_github_repository("https://github.com/octocat/demo")


def test_index_public_github_repository_returns_clean_not_found_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        "app.services.public_repository_indexer.urlopen",
        fake_urlopen,
    )

    with pytest.raises(RepositoryArchiveNotFoundError):
        index_public_github_repository("https://github.com/octocat/private")
