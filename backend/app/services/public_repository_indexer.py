import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.models import Repository
from app.services.database_writer import DatabaseWriteError, DatabaseWriter
from app.services.repository_indexer import RepositoryIndexer

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 5000
DOWNLOAD_CHUNK_BYTES = 1024 * 1024


class PublicRepositoryIndexError(RuntimeError):
    pass


class InvalidPublicRepositoryUrlError(PublicRepositoryIndexError):
    pass


class RepositoryArchiveNotFoundError(PublicRepositoryIndexError):
    pass


class RepositoryArchiveTooLargeError(PublicRepositoryIndexError):
    pass


class RepositoryArchiveError(PublicRepositoryIndexError):
    pass


@dataclass(frozen=True)
class PublicRepositoryMetadata:
    owner: str
    name: str
    url: str


@dataclass(frozen=True)
class PublicRepositoryIndexSummary:
    repository: Repository
    total_files: int
    total_chunks: int
    skipped_files: int


class _ExtractedRepositoryLoader:
    def __init__(self, repository_path: Path) -> None:
        self.repository_path = repository_path

    def load(self, source: str) -> Path:
        return self.repository_path


def index_public_github_repository(
    repository_url: str,
    *,
    writer: DatabaseWriter | None = None,
) -> PublicRepositoryIndexSummary:
    metadata = parse_public_github_repository_url(repository_url)
    writer = writer or DatabaseWriter()

    with tempfile.TemporaryDirectory(prefix="repopilot-archive-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        archive_path = temp_dir / "repository.zip"
        extract_dir = temp_dir / "source"

        _download_repository_archive(metadata, archive_path)
        repository_path = _extract_repository_archive(archive_path, extract_dir)
        result = RepositoryIndexer(
            loader=_ExtractedRepositoryLoader(repository_path),
        ).index(str(repository_path))
        try:
            repository = writer.write(
                result,
                owner=metadata.owner,
                name=metadata.name,
                url=metadata.url,
                default_branch=None,
            )
        except DatabaseWriteError as exc:
            raise PublicRepositoryIndexError(
                "Failed to persist repository index."
            ) from exc

    return PublicRepositoryIndexSummary(
        repository=repository,
        total_files=result.total_files,
        total_chunks=result.total_chunks,
        skipped_files=result.skipped_files,
    )


def parse_public_github_repository_url(repository_url: str) -> PublicRepositoryMetadata:
    parsed_url = urlparse(repository_url.strip())
    if parsed_url.scheme != "https" or parsed_url.netloc != "github.com":
        raise InvalidPublicRepositoryUrlError(
            "Repository URL must be an HTTPS GitHub URL."
        )

    if parsed_url.query or parsed_url.fragment or parsed_url.params:
        raise InvalidPublicRepositoryUrlError(
            "Repository URL must not include query strings or fragments."
        )

    path_parts = [part for part in parsed_url.path.split("/") if part]
    if len(path_parts) != 2:
        raise InvalidPublicRepositoryUrlError(
            "GitHub URL must be in the form https://github.com/owner/repository."
        )

    owner, repository_name = path_parts
    repository_name = repository_name.removesuffix(".git")
    if not owner or not repository_name:
        raise InvalidPublicRepositoryUrlError(
            "GitHub URL must include both an owner and repository name."
        )

    return PublicRepositoryMetadata(
        owner=owner,
        name=repository_name,
        url=f"https://github.com/{owner}/{repository_name}",
    )


def _download_repository_archive(
    metadata: PublicRepositoryMetadata,
    archive_path: Path,
) -> None:
    request = Request(
        f"https://api.github.com/repos/{metadata.owner}/{metadata.name}/zipball",
        headers={"User-Agent": "RepoPilot"},
    )

    try:
        with urlopen(request, timeout=30) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_ARCHIVE_BYTES:
                raise RepositoryArchiveTooLargeError(
                    "Repository archive is too large to index."
                )

            bytes_read = 0
            with archive_path.open("wb") as archive_file:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break

                    bytes_read += len(chunk)
                    if bytes_read > MAX_ARCHIVE_BYTES:
                        raise RepositoryArchiveTooLargeError(
                            "Repository archive is too large to index."
                        )
                    archive_file.write(chunk)
    except HTTPError as exc:
        if exc.code == 404:
            raise RepositoryArchiveNotFoundError(
                "Repository was not found or is not public."
            ) from exc
        raise RepositoryArchiveError("Failed to download repository archive.") from exc
    except URLError as exc:
        raise RepositoryArchiveError("Failed to download repository archive.") from exc


def _extract_repository_archive(archive_path: Path, extract_dir: Path) -> Path:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_FILES:
                raise RepositoryArchiveTooLargeError(
                    "Repository archive contains too many files."
                )

            total_size = sum(member.file_size for member in members)
            if total_size > MAX_EXTRACTED_BYTES:
                raise RepositoryArchiveTooLargeError(
                    "Repository archive is too large to index."
                )

            for member in members:
                _validate_archive_member(member)

            archive.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise RepositoryArchiveError("Repository archive is not a valid zip file.") from exc

    top_level_entries = list(extract_dir.iterdir())
    if len(top_level_entries) == 1 and top_level_entries[0].is_dir():
        return top_level_entries[0]

    return extract_dir


def _validate_archive_member(member: zipfile.ZipInfo) -> None:
    member_path = Path(member.filename)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise RepositoryArchiveError("Repository archive contains an unsafe path.")
