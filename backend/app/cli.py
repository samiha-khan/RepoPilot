from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import typer
from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo

from app.services.database_writer import DatabaseWriteError, DatabaseWriter
from app.services.repository_indexer import RepositoryIndexer
from app.services.repository_loader import (
    InvalidRepositorySourceError,
    RepositoryCloneError,
)

app = typer.Typer()


class MetadataResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class _RepositoryMetadata:
    owner: str
    name: str
    url: str


@app.callback()
def main() -> None:
    pass


@app.command()
def index(
    repository: str,
    owner: str | None = typer.Option(None, "--owner"),
    name: str | None = typer.Option(None, "--name"),
    url: str | None = typer.Option(None, "--url"),
    default_branch: str | None = typer.Option(None, "--default-branch"),
) -> None:
    try:
        result = RepositoryIndexer().index(repository)
        metadata = _resolve_repository_metadata(
            source=repository,
            repository_path=result.repository_path,
            owner=owner,
            name=name,
            url=url,
        )
        persisted_repository = DatabaseWriter().write(
            result,
            owner=metadata.owner,
            name=metadata.name,
            url=metadata.url,
            default_branch=default_branch,
        )
    except (
        InvalidRepositorySourceError,
        RepositoryCloneError,
        MetadataResolutionError,
        DatabaseWriteError,
        OSError,
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
    typer.echo(f"Persisted repository ID: {persisted_repository.id}")


def _resolve_repository_metadata(
    *,
    source: str,
    repository_path: Path,
    owner: str | None,
    name: str | None,
    url: str | None,
) -> _RepositoryMetadata:
    inferred = _parse_github_https_url(source) or _infer_local_repository_metadata(
        repository_path
    )

    resolved_owner = _clean_metadata_value(owner) or (inferred.owner if inferred else None)
    resolved_name = _clean_metadata_value(name) or (inferred.name if inferred else None)
    resolved_url = _normalize_metadata_url(url) or (inferred.url if inferred else None)

    if not resolved_owner or not resolved_name or not resolved_url:
        raise MetadataResolutionError(
            "Repository metadata could not be resolved. Provide --owner, --name, and --url."
        )

    return _RepositoryMetadata(
        owner=resolved_owner,
        name=resolved_name,
        url=resolved_url,
    )


def _infer_local_repository_metadata(repository_path: Path) -> _RepositoryMetadata | None:
    try:
        repo = Repo(repository_path)
        origin = next((remote for remote in repo.remotes if remote.name == "origin"), None)
        if origin is None:
            return None
        origin_url = next(origin.urls, None)
    except (AttributeError, GitCommandError, InvalidGitRepositoryError, NoSuchPathError):
        return None

    if origin_url is None:
        return None

    return _parse_github_origin_url(origin_url)


def _parse_github_https_url(source: str) -> _RepositoryMetadata | None:
    parsed_url = urlparse(source.strip())
    if parsed_url.scheme != "https" or parsed_url.netloc != "github.com":
        return None

    if parsed_url.query or parsed_url.fragment or parsed_url.params:
        return None

    path_parts = [part for part in parsed_url.path.split("/") if part]
    if len(path_parts) != 2:
        return None

    owner, repository_name = path_parts
    repository_name = repository_name.removesuffix(".git")
    if not owner or not repository_name:
        return None

    return _RepositoryMetadata(
        owner=owner,
        name=repository_name,
        url=f"https://github.com/{owner}/{repository_name}",
    )


def _parse_github_origin_url(origin_url: str) -> _RepositoryMetadata | None:
    origin_url = origin_url.strip()
    https_metadata = _parse_github_https_url(origin_url)
    if https_metadata is not None:
        return https_metadata

    prefix = "git@github.com:"
    if not origin_url.startswith(prefix):
        return None

    path = origin_url.removeprefix(prefix).strip("/")
    path_parts = [part for part in path.split("/") if part]
    if len(path_parts) != 2:
        return None

    owner, repository_name = path_parts
    repository_name = repository_name.removesuffix(".git")
    if not owner or not repository_name:
        return None

    return _RepositoryMetadata(
        owner=owner,
        name=repository_name,
        url=f"https://github.com/{owner}/{repository_name}",
    )


def _clean_metadata_value(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()
    return value or None


def _normalize_metadata_url(value: str | None) -> str | None:
    value = _clean_metadata_value(value)
    if value is None:
        return None

    metadata = _parse_github_https_url(value.rstrip("/"))
    if metadata is not None:
        return metadata.url

    return value.rstrip("/")


if __name__ == "__main__":
    app()
