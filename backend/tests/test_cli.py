from typer.testing import CliRunner

from app.cli import app


def test_index_command() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["index", "owner/repo"])

    assert result.exit_code == 0
    assert result.stdout == "Indexing repository: owner/repo\n"
