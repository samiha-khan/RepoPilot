from pathlib import Path
from unittest.mock import patch

import pytest
from git import GitCommandError, Repo

from app.services.repository_loader import (
    InvalidRepositorySourceError,
    RepositoryCloneError,
    RepositoryLoader,
)


def test_load_valid_local_repository(tmp_path: Path) -> None:
    Repo.init(tmp_path)

    loaded_path = RepositoryLoader().load(str(tmp_path))

    assert loaded_path == tmp_path.resolve()


def test_load_existing_directory_that_is_not_git_repository(tmp_path: Path) -> None:
    with pytest.raises(InvalidRepositorySourceError, match="not a Git repository"):
        RepositoryLoader().load(str(tmp_path))


def test_load_nonexistent_local_looking_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-repository"

    with pytest.raises(InvalidRepositorySourceError, match="does not exist"):
        RepositoryLoader().load(str(missing_path))


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/openai/repopilot",
        "https://github.com/openai/repopilot.git",
    ],
)
def test_load_valid_github_url(url: str) -> None:
    with patch("app.services.repository_loader.Repo.clone_from") as clone_from:
        loaded_path = RepositoryLoader().load(url)

    assert loaded_path.name.startswith("repopilot-")
    assert loaded_path.exists()
    clone_from.assert_called_once_with(url, loaded_path)

    loaded_path.rmdir()


def test_load_rejects_unsupported_host() -> None:
    with pytest.raises(InvalidRepositorySourceError, match="HTTPS GitHub URL"):
        RepositoryLoader().load("https://example.com/openai/repopilot")


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/openai",
        "https://github.com/openai/repopilot/tree/main",
        "https://github.com/openai/repopilot?tab=readme",
        "https://github.com/openai/repopilot#readme",
    ],
)
def test_load_rejects_malformed_github_path(url: str) -> None:
    with pytest.raises(InvalidRepositorySourceError):
        RepositoryLoader().load(url)


def test_clone_failure_removes_temporary_directory(tmp_path: Path) -> None:
    clone_path = tmp_path / "repopilot-clone"

    def fake_mkdtemp(prefix: str) -> str:
        assert prefix == "repopilot-"
        clone_path.mkdir()
        return str(clone_path)

    clone_error = GitCommandError("clone", 128, stderr="clone failed")

    with (
        patch("app.services.repository_loader.tempfile.mkdtemp", side_effect=fake_mkdtemp),
        patch("app.services.repository_loader.Repo.clone_from", side_effect=clone_error),
    ):
        with pytest.raises(RepositoryCloneError, match="Failed to clone repository"):
            RepositoryLoader().load("https://github.com/openai/repopilot")

    assert not clone_path.exists()
