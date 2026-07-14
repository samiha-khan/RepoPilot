from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from git import Repo
from typer.testing import CliRunner

from app.cli import app
from app.services.database_writer import DatabaseWriteError
from app.services.repository_indexer import RepositoryIndexResult


def make_index_result(repository_path: Path) -> RepositoryIndexResult:
    return RepositoryIndexResult(
        repository_path=repository_path.resolve(),
        files=(),
        total_files=2,
        total_chunks=5,
        skipped_files=1,
    )


def invoke_index(
    args: list[str],
    *,
    index_result: RepositoryIndexResult,
    writer_error: Exception | None = None,
):
    runner = CliRunner()

    with (
        patch("app.cli.RepositoryIndexer") as indexer_class,
        patch("app.cli.DatabaseWriter") as writer_class,
    ):
        indexer_class.return_value.index.return_value = index_result
        if writer_error is None:
            writer_class.return_value.write.return_value = SimpleNamespace(id=42)
        else:
            writer_class.return_value.write.side_effect = writer_error

        result = runner.invoke(app, ["index", *args])

    return result, indexer_class, writer_class


def test_index_command_infers_metadata_from_github_https_source(tmp_path: Path) -> None:
    index_result = make_index_result(tmp_path)

    result, indexer_class, writer_class = invoke_index(
        ["https://github.com/octocat/hello-world.git"],
        index_result=index_result,
    )

    assert result.exit_code == 0
    indexer_class.return_value.index.assert_called_once_with(
        "https://github.com/octocat/hello-world.git"
    )
    writer_class.return_value.write.assert_called_once_with(
        index_result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
        default_branch=None,
    )


def test_index_command_infers_metadata_from_local_https_origin(tmp_path: Path) -> None:
    Repo.init(tmp_path).create_remote(
        "origin",
        "https://github.com/octocat/hello-world.git",
    )
    index_result = make_index_result(tmp_path)

    result, _, writer_class = invoke_index(["/repo"], index_result=index_result)

    assert result.exit_code == 0
    writer_class.return_value.write.assert_called_once_with(
        index_result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
        default_branch=None,
    )


def test_index_command_infers_metadata_from_local_ssh_origin(tmp_path: Path) -> None:
    Repo.init(tmp_path).create_remote("origin", "git@github.com:octocat/hello-world.git")
    index_result = make_index_result(tmp_path)

    result, _, writer_class = invoke_index(["/repo"], index_result=index_result)

    assert result.exit_code == 0
    writer_class.return_value.write.assert_called_once_with(
        index_result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/octocat/hello-world",
        default_branch=None,
    )


def test_index_command_explicit_metadata_overrides_inferred_values(
    tmp_path: Path,
) -> None:
    Repo.init(tmp_path).create_remote("origin", "git@github.com:octocat/hello-world.git")
    index_result = make_index_result(tmp_path)

    result, _, writer_class = invoke_index(
        [
            "/repo",
            "--owner",
            "override-owner",
            "--name",
            "override-name",
            "--url",
            "https://github.com/override-owner/override-name.git/",
            "--default-branch",
            "trunk",
        ],
        index_result=index_result,
    )

    assert result.exit_code == 0
    writer_class.return_value.write.assert_called_once_with(
        index_result,
        owner="override-owner",
        name="override-name",
        url="https://github.com/override-owner/override-name",
        default_branch="trunk",
    )


def test_index_command_partial_explicit_override(tmp_path: Path) -> None:
    Repo.init(tmp_path).create_remote("origin", "git@github.com:octocat/hello-world.git")
    index_result = make_index_result(tmp_path)

    result, _, writer_class = invoke_index(
        ["/repo", "--url", "https://github.com/custom/location"],
        index_result=index_result,
    )

    assert result.exit_code == 0
    writer_class.return_value.write.assert_called_once_with(
        index_result,
        owner="octocat",
        name="hello-world",
        url="https://github.com/custom/location",
        default_branch=None,
    )


def test_index_command_missing_origin_requires_metadata_flags(tmp_path: Path) -> None:
    Repo.init(tmp_path)
    index_result = make_index_result(tmp_path)

    result, _, writer_class = invoke_index(["/repo"], index_result=index_result)

    assert result.exit_code == 1
    assert "Repository metadata could not be resolved" in result.stderr
    writer_class.return_value.write.assert_not_called()


def test_index_command_unsupported_origin_requires_metadata_flags(tmp_path: Path) -> None:
    Repo.init(tmp_path).create_remote("origin", "https://example.com/octocat/repo.git")
    index_result = make_index_result(tmp_path)

    result, _, writer_class = invoke_index(["/repo"], index_result=index_result)

    assert result.exit_code == 1
    assert "Repository metadata could not be resolved" in result.stderr
    writer_class.return_value.write.assert_not_called()


def test_index_command_successful_persistence_prints_summary(tmp_path: Path) -> None:
    index_result = make_index_result(tmp_path)

    result, _, _ = invoke_index(
        ["https://github.com/octocat/hello-world"],
        index_result=index_result,
    )

    assert result.exit_code == 0
    assert result.stdout == (
        "Repository indexed successfully\n"
        "\n"
        f"Repository: {tmp_path.resolve()}\n"
        "\n"
        "Python files: 2\n"
        "Code chunks: 5\n"
        "Skipped files: 1\n"
        "Persisted repository ID: 42\n"
    )


def test_index_command_database_write_failure_exits_nonzero(tmp_path: Path) -> None:
    index_result = make_index_result(tmp_path)

    result, _, _ = invoke_index(
        ["https://github.com/octocat/hello-world"],
        index_result=index_result,
        writer_error=DatabaseWriteError("write failed"),
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "Indexing failed: write failed\n"
