"""Pinned third-party corpora and conversion of source trees into chunk records."""

import json
import subprocess
from pathlib import Path

from app.search import ChunkRecord
from app.services.repository_indexer import RepositoryIndexer

EVALUATION_ROOT = Path(__file__).resolve().parent
CORPORA_FILE = EVALUATION_ROOT / "corpora.json"
CHECKOUT_ROOT = EVALUATION_ROOT / ".corpora"


class _FixedPathLoader:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self, source: str) -> Path:
        return self.path


def load_specs() -> dict[str, dict[str, str]]:
    return json.loads(CORPORA_FILE.read_text())


def fetch(name: str) -> Path:
    """Check out the pinned commit of a corpus (no-op if already present)."""
    spec = load_specs()[name]
    target = CHECKOUT_ROOT / name
    if (target / ".git").exists():
        head = _git(target, "rev-parse", "HEAD").strip()
        if head == spec["commit"]:
            return target
        raise RuntimeError(f"{target} is at {head}, expected {spec['commit']}")

    target.mkdir(parents=True, exist_ok=True)
    _git(target, "init", "-q")
    _git(target, "fetch", "-q", "--depth", "1", spec["url"], spec["commit"])
    _git(target, "checkout", "-q", "FETCH_HEAD")
    return target


def records_from_directory(root: Path, scope: str = ".") -> list[ChunkRecord]:
    """Index a source tree with the production indexer and return chunk records.

    Paths are relative to ``root``. ``scope`` limits indexing to a subdirectory
    (for example the library package without its tests).
    """
    indexed = RepositoryIndexer(loader=_FixedPathLoader(root / scope)).index("")
    prefix = "" if scope in {".", ""} else scope.rstrip("/") + "/"

    records: list[ChunkRecord] = []
    for source_file in indexed.files:
        for chunk in source_file.chunks:
            records.append(
                ChunkRecord(
                    chunk_id=len(records) + 1,
                    path=prefix + source_file.path,
                    symbol_name=chunk.symbol_name,
                    symbol_type=chunk.symbol_type,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    docstring=chunk.docstring,
                    source_code=chunk.source_code,
                )
            )
    return records


def _git(directory: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=directory,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
