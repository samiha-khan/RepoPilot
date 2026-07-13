import typer

app = typer.Typer()


@app.callback()
def main() -> None:
    pass


@app.command()
def index(repository: str) -> None:
    typer.echo(f"Indexing repository: {repository}")


if __name__ == "__main__":
    app()
