import json
import math
from typing import Protocol


EMBEDDING_MODEL = "jinaai/jina-embeddings-v2-base-code"
# bge retrieval models expect this on the query only. The code model does not.
QUERY_PREFIXES = {
    "BAAI/bge-small-en-v1.5": "Represent this sentence for searching relevant passages: ",
}


class Embedder(Protocol):
    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Vector for each indexed code chunk."""

    def embed_query(self, text: str) -> list[float]:
        """Vector for a search query."""


def embedding_text(
    *,
    symbol_name: str,
    symbol_type: str,
    path: str,
    docstring: str | None,
    source_code: str,
) -> str:
    summary = docstring.strip() if docstring else ""
    source = source_code.strip()[:2000]
    return (
        f"{symbol_type} {symbol_name}\n"
        f"file: {path}\n"
        f"{summary}\n"
        f"{source}"
    ).strip()


def encode_embedding(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))


def decode_embedding(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    try:
        return [float(item) for item in parsed]
    except (TypeError, ValueError):
        return None


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left, right):
        dot += left_value * right_value
        left_norm += left_value * left_value
        right_norm += right_value * right_value
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / math.sqrt(left_norm * right_norm)


class FastEmbedder:
    """Local ONNX embedder. The model downloads once, then runs on CPU."""

    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)
        self._query_prefix = QUERY_PREFIXES.get(model_name, "")

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [_as_floats(vector) for vector in self._model.passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        vector = next(iter(self._model.query_embed(f"{self._query_prefix}{text}")))
        return _as_floats(vector)


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = FastEmbedder()
    return _embedder


def _as_floats(vector: object) -> list[float]:
    return [float(value) for value in vector]
