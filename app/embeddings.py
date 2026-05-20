"""Local sentence-transformers embeddings (single model for RAG + cache)."""
from __future__ import annotations

import threading
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import get_settings

_lock = threading.Lock()
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    with _lock:
        if _model is None:
            name = get_settings().embedding_model
            _model = SentenceTransformer(name)
    return _model


def embed_text(text: str) -> list[float]:
    m = get_model()
    v = m.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return np.asarray(v, dtype=np.float32).tolist()


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    m = get_model()
    mat = m.encode(list(texts), convert_to_numpy=True, normalize_embeddings=True)
    return [np.asarray(row, dtype=np.float32).tolist() for row in mat]
