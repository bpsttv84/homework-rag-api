"""Build Qdrant chunk index from data/source.md (or optional PDF). Sync — safe for threads/subprocess."""
from __future__ import annotations

from pathlib import Path

import tiktoken
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import Settings
from app.embeddings import embed_texts


def _read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


def _chunk_tokens(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    if not tokens:
        return []
    pieces: list[str] = []
    step = max(1, chunk_size - overlap)
    start = 0
    while start < len(tokens):
        chunk = tokens[start : start + chunk_size]
        pieces.append(enc.decode(chunk))
        start += step
    return pieces


def run_index(settings: Settings) -> int:
    text = _read_document(settings.source_document)
    pieces = _chunk_tokens(text, chunk_size=500, overlap=50)
    if not pieces:
        raise RuntimeError("No text to index — check data/source.md")

    kwargs: dict = {"url": settings.qdrant_url}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    client = QdrantClient(**kwargs, check_compatibility=False)
    name = settings.qdrant_chunks_collection
    cols = {c.name for c in client.get_collections().collections}
    if name in cols:
        client.delete_collection(collection_name=name)
    client.create_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=384, distance=qm.Distance.COSINE),
    )

    # Qdrant 1.12 accepts only unsigned integer or UUID point IDs (not strings like "chunk_0").
    ids = list(range(len(pieces)))
    vectors = embed_texts(pieces)
    payloads = [
        {"text": chunk, "source": str(settings.source_document), "chunk_index": i}
        for i, chunk in enumerate(pieces)
    ]
    points = [
        qm.PointStruct(id=pid, vector=vec, payload=pay)
        for pid, vec, pay in zip(ids, vectors, payloads, strict=True)
    ]
    client.upsert(collection_name=name, points=points)
    return len(points)
