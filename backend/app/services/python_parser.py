import ast
from dataclasses import dataclass
from pathlib import Path


class PythonParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedCodeChunk:
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int
    source_code: str
    docstring: str | None


def parse_file(path: Path) -> list[ParsedCodeChunk]:
    if not path.exists():
        raise PythonParseError(f"Python source file does not exist: {path}")

    if not path.is_file():
        raise PythonParseError(f"Python source path is not a file: {path}")

    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PythonParseError(f"Python source file is not valid UTF-8: {path}") from exc

    try:
        return parse_source(source)
    except PythonParseError as exc:
        raise PythonParseError(f"{path}: {exc}") from exc


def parse_source(source: str) -> list[ParsedCodeChunk]:
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise PythonParseError(f"Invalid Python syntax: {exc.msg}") from exc

    chunks: list[ParsedCodeChunk] = []
    for node in module.body:
        if isinstance(node, ast.FunctionDef):
            chunks.append(_build_chunk(source, node, "function"))
        elif isinstance(node, ast.AsyncFunctionDef):
            chunks.append(_build_chunk(source, node, "async_function"))
        elif isinstance(node, ast.ClassDef):
            # Class chunks span the full class body; direct methods are emitted separately.
            chunks.append(_build_chunk(source, node, "class"))
            chunks.extend(_parse_class_methods(source, node))

    return chunks


def _parse_class_methods(source: str, class_node: ast.ClassDef) -> list[ParsedCodeChunk]:
    chunks: list[ParsedCodeChunk] = []
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef):
            chunks.append(_build_chunk(source, node, "method"))
        elif isinstance(node, ast.AsyncFunctionDef):
            chunks.append(_build_chunk(source, node, "async_method"))

    return chunks


def _build_chunk(
    source: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    symbol_type: str,
) -> ParsedCodeChunk:
    if node.end_lineno is None:
        raise PythonParseError(f"Missing end line for symbol: {node.name}")

    return ParsedCodeChunk(
        symbol_name=node.name,
        symbol_type=symbol_type,
        start_line=_get_start_line(node),
        end_line=node.end_lineno,
        source_code=_get_source_code(source, node),
        docstring=ast.get_docstring(node),
    )


def _get_source_code(
    source: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> str:
    source_segment = ast.get_source_segment(source, node)
    if source_segment is not None and not node.decorator_list:
        return source_segment

    lines = source.splitlines()
    return "\n".join(lines[_get_start_line(node) - 1 : node.end_lineno])


def _get_start_line(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> int:
    if node.decorator_list:
        return node.decorator_list[0].lineno

    return node.lineno
