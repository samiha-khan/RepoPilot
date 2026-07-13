import hashlib
from pathlib import Path

from git import Repo

from app.services.repository_indexer import RepositoryIndexer


class FakeRepositoryLoader:
    def __init__(self, repository_path: Path) -> None:
        self.repository_path = repository_path
        self.loaded_sources: list[str] = []

    def load(self, source: str) -> Path:
        self.loaded_sources.append(source)
        return self.repository_path


def write_file(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def test_indexes_small_temporary_git_repository(tmp_path: Path) -> None:
    Repo.init(tmp_path)
    write_file(
        tmp_path / "app.py",
        "def main():\n"
        "    return 'ok'\n",
    )

    result = RepositoryIndexer().index(str(tmp_path))

    assert result.repository_path == tmp_path.resolve()
    assert result.total_files == 1
    assert result.total_chunks == 1
    assert result.skipped_files == 0
    assert result.files[0].path == "app.py"
    assert result.files[0].language == "python"
    assert result.files[0].chunks[0].symbol_name == "main"


def test_finds_nested_python_files_with_mocked_loader(tmp_path: Path) -> None:
    loader = FakeRepositoryLoader(tmp_path)
    write_file(tmp_path / "pkg" / "module.py", "class Service:\n    pass\n")

    result = RepositoryIndexer(loader=loader).index("mock-source")

    assert loader.loaded_sources == ["mock-source"]
    assert [file.path for file in result.files] == ["pkg/module.py"]
    assert result.files[0].chunks[0].symbol_name == "Service"


def test_ignores_excluded_directories(tmp_path: Path) -> None:
    write_file(tmp_path / "app.py", "def included():\n    pass\n")
    for directory in [
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
    ]:
        write_file(tmp_path / directory / "ignored.py", "def ignored():\n    pass\n")

    result = RepositoryIndexer(loader=FakeRepositoryLoader(tmp_path)).index("mock-source")

    assert [file.path for file in result.files] == ["app.py"]
    assert result.total_files == 1


def test_preserves_deterministic_ordering_by_relative_path(tmp_path: Path) -> None:
    write_file(tmp_path / "z.py", "def z():\n    pass\n")
    write_file(tmp_path / "a" / "b.py", "def b():\n    pass\n")
    write_file(tmp_path / "a" / "a.py", "def a():\n    pass\n")

    result = RepositoryIndexer(loader=FakeRepositoryLoader(tmp_path)).index("mock-source")

    assert [file.path for file in result.files] == ["a/a.py", "a/b.py", "z.py"]


def test_computes_sha256_and_size_from_raw_bytes(tmp_path: Path) -> None:
    contents = "def checksum():\n    return 'ok'\n"
    path = write_file(tmp_path / "checksum.py", contents)
    raw_bytes = path.read_bytes()

    result = RepositoryIndexer(loader=FakeRepositoryLoader(tmp_path)).index("mock-source")

    assert result.files[0].sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert result.files[0].size == len(raw_bytes)


def test_aggregates_total_files_and_total_chunks(tmp_path: Path) -> None:
    write_file(
        tmp_path / "one.py",
        "def one():\n"
        "    pass\n",
    )
    write_file(
        tmp_path / "two.py",
        "class Two:\n"
        "    def method(self):\n"
        "        pass\n",
    )

    result = RepositoryIndexer(loader=FakeRepositoryLoader(tmp_path)).index("mock-source")

    assert result.total_files == 2
    assert result.total_chunks == 3
    assert result.skipped_files == 0


def test_invalid_python_file_is_skipped_without_failing_index(tmp_path: Path) -> None:
    write_file(tmp_path / "valid.py", "def valid():\n    pass\n")
    write_file(tmp_path / "invalid.py", "def broken(:\n")

    result = RepositoryIndexer(loader=FakeRepositoryLoader(tmp_path)).index("mock-source")

    assert [file.path for file in result.files] == ["valid.py"]
    assert result.total_files == 1
    assert result.total_chunks == 1
    assert result.skipped_files == 1


def test_symlinked_python_file_outside_repository_is_ignored(tmp_path: Path) -> None:
    outside_path = write_file(tmp_path.parent / "outside.py", "def outside():\n    pass\n")
    (tmp_path / "linked.py").symlink_to(outside_path)
    write_file(tmp_path / "inside.py", "def inside():\n    pass\n")

    result = RepositoryIndexer(loader=FakeRepositoryLoader(tmp_path)).index("mock-source")

    assert [file.path for file in result.files] == ["inside.py"]
    assert result.skipped_files == 0
