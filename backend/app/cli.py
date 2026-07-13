import typer

from app.services.repository_indexer import RepositoryIndexer
from app.services.repository_loader import (
    InvalidRepositorySourceError,
    RepositoryCloneError,
)

app = typer.Typer()


@app.callback()
def main() -> None:
    pass


@app.command()
def index(repository: str) -> None:
    try:
        result = RepositoryIndexer().index(repository)
    except (
        InvalidRepositorySourceError,
        RepositoryCloneError,
        OSError,
        ValueError,
    ) as exc:
        typer.secho(f"Indexing failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Repository indexed successfully")
    typer.echo()
    typer.echo(f"Repository: {result.repository_path}")
    typer.echo()
    typer.echo(f"Python files: {result.total_files}")
    typer.echo(f"Code chunks: {result.total_chunks}")
    typer.echo(f"Skipped files: {result.skipped_files}")


if __name__ == "__main__":
    app()
