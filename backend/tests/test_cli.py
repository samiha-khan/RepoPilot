from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from app.cli import app
from app.services.repository_indexer import RepositoryIndexResult


def test_index_command_success() -> None:
    runner = CliRunner()
    index_result = RepositoryIndexResult(
        repository_path=Path("/tmp/repo").resolve(),
        files=(),
        total_files=2,
        total_chunks=5,
        skipped_files=1,
    )

    with patch("app.cli.RepositoryIndexer") as indexer_class:
        indexer_class.return_value.index.return_value = index_result

        result = runner.invoke(app, ["index", "owner/repo"])

    assert result.exit_code == 0
    assert result.stdout == (
        "Repository indexed successfully\n"
        "\n"
        f"Repository: {Path('/tmp/repo').resolve()}\n"
        "\n"
        "Python files: 2\n"
        "Code chunks: 5\n"
        "Skipped files: 1\n"
    )
    indexer_class.assert_called_once_with()
    indexer_class.return_value.index.assert_called_once_with("owner/repo")


def test_index_command_failure() -> None:
    runner = CliRunner()

    with patch("app.cli.RepositoryIndexer") as indexer_class:
        indexer_class.return_value.index.side_effect = ValueError("bad repository")

        result = runner.invoke(app, ["index", "owner/repo"])

    assert result.exit_code == 1
    assert result.stderr == "Indexing failed: bad repository\n"
    indexer_class.assert_called_once_with()
    indexer_class.return_value.index.assert_called_once_with("owner/repo")
