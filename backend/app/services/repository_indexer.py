import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.services.python_parser import ParsedCodeChunk, PythonParseError, parse_file
from app.services.repository_loader import RepositoryLoader

EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
}


@dataclass(frozen=True)
class IndexedSourceFile:
    path: str
    language: str
    sha256: str
    size: int
    chunks: tuple[ParsedCodeChunk, ...]


@dataclass(frozen=True)
class RepositoryIndexResult:
    repository_path: Path
    files: tuple[IndexedSourceFile, ...]
    total_files: int
    total_chunks: int
    skipped_files: int


class RepositoryIndexer:
    def __init__(self, loader: RepositoryLoader | None = None) -> None:
        self.loader = loader or RepositoryLoader()

    def index(self, source: str) -> RepositoryIndexResult:
        repository_path = self.loader.load(source).resolve()
        if not repository_path.exists() or not repository_path.is_dir():
            raise ValueError(f"Repository path is not an existing directory: {repository_path}")

        indexed_files: list[IndexedSourceFile] = []
        skipped_files = 0

        for path in self._find_python_files(repository_path):
            try:
                raw_bytes = path.read_bytes()
                chunks = tuple(parse_file(path))
            except (OSError, PythonParseError):
                skipped_files += 1
                continue

            indexed_files.append(
                IndexedSourceFile(
                    path=path.relative_to(repository_path).as_posix(),
                    language="python",
                    sha256=hashlib.sha256(raw_bytes).hexdigest(),
                    size=len(raw_bytes),
                    chunks=chunks,
                )
            )

        files = tuple(indexed_files)
        return RepositoryIndexResult(
            repository_path=repository_path,
            files=files,
            total_files=len(files),
            total_chunks=sum(len(file.chunks) for file in files),
            skipped_files=skipped_files,
        )

    def _find_python_files(self, repository_path: Path) -> list[Path]:
        files: list[Path] = []
        for path in repository_path.rglob("*.py"):
            if self._is_excluded(path, repository_path):
                continue

            if not self._is_inside_repository(path, repository_path):
                continue

            files.append(path)

        return sorted(files, key=lambda path: path.relative_to(repository_path).as_posix())

    def _is_excluded(self, path: Path, repository_path: Path) -> bool:
        relative_parts = path.relative_to(repository_path).parts
        return any(part in EXCLUDED_DIRECTORIES for part in relative_parts)

    def _is_inside_repository(self, path: Path, repository_path: Path) -> bool:
        try:
            path.resolve().relative_to(repository_path)
        except ValueError:
            return False

        return True
