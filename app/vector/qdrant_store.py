"""Qdrant: chunks collection + semantic cache collection."""
from __future__ import annotations

import time
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from app.config import Settings


class QdrantStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        kwargs: dict[str, Any] = {"url": settings.qdrant_url}
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key
        self._client = AsyncQdrantClient(**kwargs, check_compatibility=False)
        self._dim = 384  # all-MiniLM-L6-v2

    async def ensure_collections(self) -> None:
        cols = await self._client.get_collections()
        existing = {c.name for c in cols.collections}
        for name in (self._settings.qdrant_chunks_collection, self._settings.qdrant_cache_collection):
            if name in existing:
                continue
            await self._client.create_collection(
                collection_name=name,
                vectors_config=qm.VectorParams(size=self._dim, distance=qm.Distance.COSINE),
            )

    async def upsert_chunks(self, ids: list[str], vectors: list[list[float]], payloads: list[dict]) -> None:
        points = [
            qm.PointStruct(id=pid, vector=vec, payload=pay)
            for pid, vec, pay in zip(ids, vectors, payloads, strict=True)
        ]
        await self._client.upsert(
            collection_name=self._settings.qdrant_chunks_collection,
            points=points,
        )

    async def search_chunks(self, vector: list[float], limit: int) -> list[tuple[str, float, dict]]:
        res = await self._client.search(
            collection_name=self._settings.qdrant_chunks_collection,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )
        out: list[tuple[str, float, dict]] = []
        for hit in res:
            sim = float(hit.score)  # cosine similarity for COSINE distance in newer qdrant? Actually score is similarity for cosine
            pid = str(hit.id)
            payload = dict(hit.payload or {})
            out.append((pid, sim, payload))
        return out

    async def search_cache(self, vector: list[float], threshold: float) -> tuple[str, str, list[str], str] | None:
        """Return (response_text, model, sources, point_id) if hit above threshold and not expired."""
        now = time.time()
        res = await self._client.search(
            collection_name=self._settings.qdrant_cache_collection,
            query_vector=vector,
            limit=3,
            with_payload=True,
        )
        for hit in res:
            if float(hit.score) < threshold:
                continue
            pay = dict(hit.payload or {})
            exp = float(pay.get("expire_at", 0))
            if exp < now:
                continue
            resp = str(pay.get("response", ""))
            model = str(pay.get("model", ""))
            sources = list(pay.get("sources") or [])
            return resp, model, sources, str(hit.id)
        return None

    async def put_cache(
        self,
        vector: list[float],
        query: str,
        response: str,
        model: str,
        sources: list[str],
        ttl_seconds: int,
    ) -> str:
        point_id = str(uuid.uuid4())
        expire_at = time.time() + ttl_seconds
        await self._client.upsert(
            collection_name=self._settings.qdrant_cache_collection,
            points=[
                qm.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "query": query[:4000],
                        "response": response,
                        "model": model,
                        "sources": sources,
                        "expire_at": expire_at,
                    },
                )
            ],
        )
        return point_id

    async def recreate_chunks_collection(self) -> None:
        name = self._settings.qdrant_chunks_collection
        cols = await self._client.get_collections()
        if name in {c.name for c in cols.collections}:
            await self._client.delete_collection(collection_name=name)
        await self._client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=self._dim, distance=qm.Distance.COSINE),
        )
