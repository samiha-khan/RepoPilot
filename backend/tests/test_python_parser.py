from pathlib import Path

import pytest

from app.services.python_parser import (
    ParsedCodeChunk,
    PythonParseError,
    parse_file,
    parse_source,
)


def test_parse_top_level_function() -> None:
    chunks = parse_source(
        "def greet(name):\n"
        "    return f'Hello, {name}'\n"
    )

    assert chunks == [
        ParsedCodeChunk(
            symbol_name="greet",
            symbol_type="function",
            start_line=1,
            end_line=2,
            source_code="def greet(name):\n    return f'Hello, {name}'",
            docstring=None,
        )
    ]


def test_parse_async_function() -> None:
    chunks = parse_source(
        "async def fetch():\n"
        "    return 'ok'\n"
    )

    assert chunks[0].symbol_name == "fetch"
    assert chunks[0].symbol_type == "async_function"


def test_parse_class_regular_method_and_async_method() -> None:
    chunks = parse_source(
        "class Worker:\n"
        "    def run(self):\n"
        "        return 'run'\n"
        "\n"
        "    async def stop(self):\n"
        "        return 'stop'\n"
    )

    assert [chunk.symbol_name for chunk in chunks] == ["Worker", "run", "stop"]
    assert [chunk.symbol_type for chunk in chunks] == ["class", "method", "async_method"]


def test_parse_docstrings() -> None:
    chunks = parse_source(
        "def documented():\n"
        "    \"\"\"Function docs.\"\"\"\n"
        "    return None\n"
        "\n"
        "class Documented:\n"
        "    \"\"\"Class docs.\"\"\"\n"
        "\n"
        "    def method(self):\n"
        "        \"\"\"Method docs.\"\"\"\n"
        "        return None\n"
    )

    assert [chunk.docstring for chunk in chunks] == [
        "Function docs.",
        "Class docs.",
        "Method docs.",
    ]


def test_parse_correct_source_code_extraction_and_line_ranges() -> None:
    chunks = parse_source(
        "# module comment\n"
        "\n"
        "def first():\n"
        "    x = 1\n"
        "    return x\n"
        "\n"
        "class Second:\n"
        "    pass\n"
    )

    assert chunks[0].start_line == 3
    assert chunks[0].end_line == 5
    assert chunks[0].source_code == "def first():\n    x = 1\n    return x"
    assert chunks[1].start_line == 7
    assert chunks[1].end_line == 8
    assert chunks[1].source_code == "class Second:\n    pass"


def test_parse_preserves_source_order() -> None:
    chunks = parse_source(
        "def first():\n"
        "    pass\n"
        "\n"
        "class Second:\n"
        "    def third(self):\n"
        "        pass\n"
        "\n"
        "async def fourth():\n"
        "    pass\n"
    )

    assert [chunk.symbol_name for chunk in chunks] == ["first", "Second", "third", "fourth"]


def test_parse_invalid_syntax() -> None:
    with pytest.raises(PythonParseError, match="Invalid Python syntax"):
        parse_source("def broken(:\n")


def test_parse_empty_source_and_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.py"
    path.write_text("", encoding="utf-8")

    assert parse_source("") == []
    assert parse_file(path) == []


def test_parse_file_rejects_nonexistent_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.py"

    with pytest.raises(PythonParseError, match=f"does not exist: {path}"):
        parse_file(path)


def test_parse_file_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(PythonParseError, match=f"not a file: {tmp_path}"):
        parse_file(tmp_path)


def test_parse_file_wraps_non_utf8_file(tmp_path: Path) -> None:
    path = tmp_path / "latin1.py"
    path.write_bytes("def café():\n    pass\n".encode("latin-1"))

    with pytest.raises(PythonParseError, match=f"not valid UTF-8: {path}"):
        parse_file(path)


def test_parse_file_includes_path_in_syntax_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n", encoding="utf-8")

    with pytest.raises(PythonParseError, match=str(path)):
        parse_file(path)


def test_decorated_function_and_class_include_decorators() -> None:
    chunks = parse_source(
        "@route('/health')\n"
        "def health():\n"
        "    return 'ok'\n"
        "\n"
        "@dataclass\n"
        "class Item:\n"
        "    name: str\n"
    )

    assert chunks[0].source_code.startswith("@route('/health')\n")
    assert chunks[0].start_line == 1
    assert chunks[1].source_code.startswith("@dataclass\n")
    assert chunks[1].start_line == 5


def test_nested_function_is_not_emitted() -> None:
    chunks = parse_source(
        "def outer():\n"
        "    def inner():\n"
        "        return 'inner'\n"
        "    return inner()\n"
    )

    assert [chunk.symbol_name for chunk in chunks] == ["outer"]


def test_nested_class_is_out_of_scope_for_now() -> None:
    chunks = parse_source(
        "class Outer:\n"
        "    class Inner:\n"
        "        pass\n"
        "\n"
        "    def method(self):\n"
        "        pass\n"
    )

    assert [chunk.symbol_name for chunk in chunks] == ["Outer", "method"]
