import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo


class InvalidRepositorySourceError(ValueError):
    pass


class RepositoryCloneError(RuntimeError):
    pass


class RepositoryLoader:
    def load(self, source: str) -> Path:
        source = source.strip()
        if not source:
            raise InvalidRepositorySourceError("Repository source cannot be empty.")

        local_path = Path(source).expanduser()
        if local_path.exists():
            return self._load_local_repository(local_path)

        if self._looks_like_url(source):
            return self._clone_github_repository(source)

        if self._looks_like_local_path(source):
            raise InvalidRepositorySourceError(f"Local repository path does not exist: {source}")

        return self._clone_github_repository(source)

    def _load_local_repository(self, path: Path) -> Path:
        resolved_path = path.resolve()
        if not resolved_path.is_dir():
            raise InvalidRepositorySourceError(
                f"Local repository path is not a directory: {resolved_path}"
            )

        try:
            repo = Repo(resolved_path)
        except (InvalidGitRepositoryError, NoSuchPathError) as exc:
            raise InvalidRepositorySourceError(
                f"Local path is not a Git repository: {resolved_path}"
            ) from exc

        if repo.bare or repo.working_tree_dir is None:
            raise InvalidRepositorySourceError(
                f"Local repository must have a working tree: {resolved_path}"
            )

        return Path(repo.working_tree_dir).resolve()

    def _clone_github_repository(self, source: str) -> Path:
        self._validate_github_url(source)
        clone_path = Path(tempfile.mkdtemp(prefix="repopilot-"))

        try:
            Repo.clone_from(source, clone_path)
        except GitCommandError as exc:
            shutil.rmtree(clone_path, ignore_errors=True)
            raise RepositoryCloneError(f"Failed to clone repository: {source}") from exc

        return clone_path

    def _validate_github_url(self, source: str) -> None:
        parsed_url = urlparse(source)
        if parsed_url.scheme != "https" or parsed_url.netloc != "github.com":
            raise InvalidRepositorySourceError(
                "Repository URL must be an HTTPS GitHub URL."
            )

        if parsed_url.query or parsed_url.fragment or parsed_url.params:
            raise InvalidRepositorySourceError(
                "Repository URL must not include query strings or fragments."
            )

        path_parts = [part for part in parsed_url.path.split("/") if part]
        if len(path_parts) != 2:
            raise InvalidRepositorySourceError(
                "GitHub URL must be in the form https://github.com/owner/repository."
            )

        owner, repository = path_parts
        if not owner or not repository:
            raise InvalidRepositorySourceError(
                "GitHub URL must include both an owner and repository name."
            )

        if repository.endswith(".git"):
            repository = repository.removesuffix(".git")

        if not repository:
            raise InvalidRepositorySourceError(
                "GitHub URL must include a repository name."
            )

    def _looks_like_local_path(self, source: str) -> bool:
        return (
            source.startswith((".", "/", "~"))
            or "/" in source
            or "\\" in source
        )

    def _looks_like_url(self, source: str) -> bool:
        parsed_url = urlparse(source)
        return bool(parsed_url.scheme or parsed_url.netloc)
