from functools import lru_cache
from typing import Protocol

import numpy as np

from app.core.config import get_settings

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
MAX_SOURCE_CHARACTERS = 2000


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        pass

    def embed_query(self, text: str) -> np.ndarray:
        pass


class FastEmbedEmbedder:
    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        vectors = np.array(list(self._get_model().passage_embed(texts)), dtype=np.float32)
        return normalize(vectors)

    def embed_query(self, text: str) -> np.ndarray:
        vector = np.array(next(iter(self._get_model().query_embed(text))), dtype=np.float32)
        return normalize(vector)

    def _get_model(self):
        # Imported here so the app still starts when fastembed isn't installed
        # and embeddings are turned off.
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self.model_name)
        return self._model


@lru_cache
def get_default_embedder() -> Embedder | None:
    settings = get_settings()
    if not settings.embeddings_enabled:
        return None
    return FastEmbedEmbedder(settings.embedding_model)


def build_chunk_text(
    *,
    symbol_name: str,
    file_path: str,
    docstring: str | None,
    source_code: str,
) -> str:
    parts = [symbol_name.replace("_", " ").strip(), file_path]
    if docstring:
        parts.append(docstring)
    parts.append(source_code[:MAX_SOURCE_CHARACTERS])
    return "\n".join(parts)


def normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def vector_to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def bytes_to_vector(value: bytes) -> np.ndarray:
    return np.frombuffer(value, dtype=np.float32)
