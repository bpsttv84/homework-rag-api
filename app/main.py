"""Production RAG API: FastAPI, SSE, Qdrant RAG + semantic cache, Redis rate limit, cost rows, Langfuse."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from redis.asyncio import Redis

from app.redis_client import create_redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth import ApiKeyContext, require_api_key
from app.config import Settings, get_settings
from app.cost import pricing
from app.cost.repository import init_schema, insert_cost_row, make_engine, usage_breakdown, usage_today
from app.embeddings import embed_text
from app.indexing import run_index
from app.llm.openrouter import OpenRouterStreamer
from app.observability import langfuse_client as lf
from app.rag import build_messages, fake_tokenize
from app import rate_limit
from app.security import postcheck_output, validate_user_message
from app.vector.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)

_metrics_lock = asyncio.Lock()
_active_streams = 0
_aborted_streams = 0


async def _inc_active() -> None:
    global _active_streams
    async with _metrics_lock:
        _active_streams += 1


async def _dec_active() -> None:
    global _active_streams
    async with _metrics_lock:
        _active_streams -= 1


async def _inc_aborted() -> None:
    global _aborted_streams
    async with _metrics_lock:
        _aborted_streams += 1


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    app.state.settings = s
    app.state.redis = create_redis(s.redis_url)
    await app.state.redis.ping()
    app.state.engine = make_engine(s.database_url)
    await init_schema(app.state.engine)
    app.state.qdrant = QdrantStore(s)
    await app.state.qdrant.ensure_collections()
    app.state.streamer = OpenRouterStreamer(s)
    app.state.llm_sem = asyncio.Semaphore(s.llm_concurrency)
    app.state.langfuse = lf.make_client(s)
    app.state.rebuild_task: asyncio.Task[None] | None = None
    yield
    await app.state.redis.aclose()
    await app.state.engine.dispose()
    await app.state.qdrant._client.close()


app = FastAPI(title="Homework RAG API", lifespan=lifespan)


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "liveness": "ok",
        "active_streams": _active_streams,
        "aborted_streams": _aborted_streams,
    }


@app.get("/usage/today")
async def usage_today_route(
    request: Request,
    api: ApiKeyContext = Depends(require_api_key),
) -> dict[str, Any]:
    async with request.app.state.engine.connect() as conn:
        return await usage_today(conn, api.raw_key)


@app.get("/usage/breakdown")
async def usage_breakdown_route(
    request: Request,
    api: ApiKeyContext = Depends(require_api_key),
) -> dict[str, Any]:
    async with request.app.state.engine.connect() as conn:
        return await usage_breakdown(conn, api.raw_key)


@app.post("/index/rebuild")
async def index_rebuild(
    request: Request,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> dict[str, str]:
    s: Settings = request.app.state.settings
    if not x_admin_key or x_admin_key != s.admin_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")
    existing = getattr(request.app.state, "rebuild_task", None)
    if existing is not None and not existing.done():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Rebuild already running")

    async def _job() -> None:
        try:
            await asyncio.to_thread(run_index, s)
            logger.info("Index rebuild finished")
        except Exception:
            logger.exception("Index rebuild failed")

    request.app.state.rebuild_task = asyncio.create_task(_job())
    return {"status": "accepted"}


@app.post("/chat/stream")
async def chat_stream(
    request: Request,
    body: ChatBody,
    api: ApiKeyContext = Depends(require_api_key),
) -> StreamingResponse:
    validate_user_message(body.message)
    s: Settings = request.app.state.settings
    r: Redis = request.app.state.redis
    estimate = min(api.tokens_per_minute, max(400, len(body.message) // 2 + 4096))
    await rate_limit.precheck_or_raise(r, api.raw_key, float(api.tokens_per_minute), estimate)

    request_id = str(uuid.uuid4())
    t0 = time.perf_counter()
    ttft_ms = 0.0
    lf_client = request.app.state.langfuse
    lf_trace = lf.start_trace(
        lf_client,
        name="rag-chat",
        input_data={"message": body.message[:4000]},
        metadata={"tier": api.tier, "request_id": request_id},
    )
    if lf_trace:
        sp = lf.span(lf_trace, "rate_limit_precheck")
        lf.finish_observation(sp, output={"estimate_tokens": estimate, "capacity_tpm": api.tokens_per_minute})

    async def event_gen() -> AsyncIterator[str]:
        nonlocal ttft_ms
        aborted = False
        full_text_parts: list[str] = []
        cache_hit = False
        fallback_used = False
        model_used = ""
        in_tok = 0
        out_tok = 0
        sources: list[str] = []
        first_token_time: float | None = None
        qdrant: QdrantStore = request.app.state.qdrant
        vec: list[float] = []

        await _inc_active()
        try:
            vec = embed_text(body.message)
            if lf_trace:
                sp = lf.span(lf_trace, "embed")
                lf.finish_observation(sp, output={"dim": len(vec)})

            hit = await qdrant.search_cache(vec, s.cache_similarity_threshold)
            if hit:
                cache_hit = True
                cached_resp, cache_model, sources, _pid = hit
                model_used = cache_model or "cache"
                if lf_trace:
                    sp = lf.span(lf_trace, "cache_lookup")
                    lf.finish_observation(sp, output={"hit": True, "sources": sources})
                for piece in fake_tokenize(cached_resp):
                    if await request.is_disconnected():
                        aborted = True
                        break
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                        ttft_ms = (first_token_time - t0) * 1000
                    full_text_parts.append(piece)
                    yield _sse({"token": piece})
                in_tok = max(1, len(body.message) // 4)
                out_tok = max(1, len(cached_resp) // 4)
            else:
                if lf_trace:
                    sp = lf.span(lf_trace, "cache_lookup")
                    lf.finish_observation(sp, output={"hit": False})

                rows = await qdrant.search_chunks(vec, s.rag_top_k)
                chunk_pairs = [(str(pid), str(payload.get("text", ""))) for pid, _score, payload in rows]
                sources = [cid for cid, _txt in chunk_pairs]
                messages = build_messages(body.message, chunk_pairs)

                if lf_trace:
                    sp = lf.span(lf_trace, "retrieve")
                    lf.finish_observation(sp, output={"top_k": len(chunk_pairs), "sources": sources})

                streamer: OpenRouterStreamer = request.app.state.streamer
                gen_span = None
                if lf_trace:
                    gen_span = lf.generation(
                        lf_trace,
                        name="llm",
                        model=api.models[0],
                        input={"messages_preview": str(messages)[:2000]},
                    )
                try:
                    async with request.app.state.llm_sem:
                        async for kind, payload in streamer.stream_chat(
                            tier=api.tier,
                            models=api.models,
                            messages=messages,
                        ):
                            if kind == "token":
                                if await request.is_disconnected():
                                    aborted = True
                                    break
                                if first_token_time is None:
                                    first_token_time = time.perf_counter()
                                    ttft_ms = (first_token_time - t0) * 1000
                                full_text_parts.append(payload)
                                yield _sse({"token": payload})
                            elif kind == "done":
                                model_used = str(payload.get("model", ""))
                                in_tok = int(payload.get("input_tokens", 0) or 0)
                                out_tok = int(payload.get("output_tokens", 0) or 0)
                                fallback_used = bool(payload.get("fallback_used"))
                except asyncio.CancelledError:
                    aborted = True
                    raise
                except BaseException as exc:  # noqa: BLE001
                    if gen_span is not None:
                        try:
                            lf.finish_observation(gen_span, output={"error": str(exc)[:500]})
                        except Exception:
                            pass
                    yield _sse({"type": "error", "detail": str(exc)})
                    if lf_trace:
                        lf.finish_observation(lf_trace, metadata={"error": str(exc)[:500]})
                    if lf_client:
                        lf_client.flush()
                    return
                else:
                    if gen_span is not None and not aborted:
                        try:
                            lf.finish_observation(
                                gen_span,
                                output="".join(full_text_parts)[:8000],
                                usage_details={
                                    "prompt_tokens": in_tok,
                                    "completion_tokens": out_tok,
                                    "total_tokens": in_tok + out_tok,
                                },
                            )
                        except Exception:
                            pass

        except asyncio.CancelledError:
            aborted = True
            raise
        except BaseException as exc:  # noqa: BLE001
            logger.exception("chat_stream failure")
            yield _sse({"type": "error", "detail": str(exc)})
            if lf_trace:
                lf.finish_observation(lf_trace, metadata={"error": str(exc)[:500]})
            if lf_client:
                lf_client.flush()
            return
        finally:
            await _dec_active()

        if aborted or await request.is_disconnected():
            await _inc_aborted()
            if lf_trace:
                lf.finish_observation(lf_trace, metadata={"aborted": True})
            if lf_client:
                lf_client.flush()
            return

        full_text = "".join(full_text_parts)
        output_filtered = postcheck_output(full_text)
        latency_ms = (time.perf_counter() - t0) * 1000

        yield _sse(
            {
                "type": "done",
                "request_id": request_id,
                "cache_hit": cache_hit,
                "sources": sources,
                "model": model_used,
                "fallback_used": fallback_used,
                "output_filtered": output_filtered,
            }
        )

        try:
            await rate_limit.consume_tokens(r, api.raw_key, float(api.tokens_per_minute), in_tok + out_tok)
        except Exception:
            logger.exception("consume_tokens failed")

        cost_usd = pricing.estimate_cost_usd(model_used, in_tok, out_tok)
        async with request.app.state.engine.begin() as conn:
            await insert_cost_row(
                conn,
                request_id=request_id,
                api_key=api.raw_key,
                model=model_used or "unknown",
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                ttft_ms=ttft_ms,
                cache_hit=cache_hit,
                fallback_used=fallback_used,
                output_filtered=output_filtered,
                tier=api.tier,
            )

        if not cache_hit and not output_filtered and full_text.strip():
            ttl = int(s.cache_ttl_hours * 3600)
            try:
                await qdrant.put_cache(vec, body.message, full_text, model_used, sources, ttl)
            except Exception:
                logger.exception("put_cache failed")

        if lf_trace:
            lf.finish_observation(
                lf_trace,
                output=full_text[:4000],
                metadata={"cache_hit": cache_hit, "fallback_used": fallback_used},
            )
        if lf_client:
            lf_client.flush()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
