"""OpenRouter streaming with timeouts, retries, and fallback models."""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import httpx
from openai import APIError, AsyncOpenAI, RateLimitError
from openai import Timeout

from app.config import Settings
from app.llm import circuit

RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def _is_retryable_exc(exc: BaseException) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIError):
        status = getattr(exc, "status_code", None)
        if status in RETRYABLE_HTTP:
            return True
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def _is_client_fatal(exc: BaseException) -> bool:
    if isinstance(exc, APIError):
        status = getattr(exc, "status_code", None)
        if status in (400, 401, 403, 422):
            return True
    return False


class OpenRouterStreamer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
            timeout=Timeout(120.0),
        )

    async def stream_chat(
        self,
        *,
        tier: str,
        models: list[str],
        messages: list[dict[str, str]],
    ) -> AsyncIterator[tuple[str, Any]]:
        """
        Yields ("token", str) for content, then ("done", dict) with keys:
        model, input_tokens, output_tokens, fallback_used
        """
        primary = models[0]
        order = list(models)
        if circuit.should_skip_primary(tier, primary):
            order = [m for m in order if m != primary] + [primary]

        last_exc: BaseException | None = None
        fallback_used = False

        for idx, model in enumerate(order):
            if idx > 0:
                fallback_used = True
            try:
                in_tok = 0
                out_tok = 0
                async for kind, payload in self._stream_one(model=model, messages=messages):
                    if kind == "usage":
                        in_tok = int(payload.get("prompt_tokens", 0) or 0)
                        out_tok = int(payload.get("completion_tokens", 0) or 0)
                        continue
                    yield kind, payload
                if model == primary:
                    circuit.record_success(tier, primary)
                yield (
                    "done",
                    {
                        "model": model,
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "fallback_used": fallback_used,
                    },
                )
                return
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # noqa: BLE001
                last_exc = exc
                if model == primary and _is_retryable_exc(exc):
                    circuit.record_failure(tier, primary)
                if _is_client_fatal(exc):
                    raise
                if not _is_retryable_exc(exc):
                    raise
                continue

        assert last_exc is not None
        raise last_exc

    async def _stream_one(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[tuple[str, Any]]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        # include_usage supported on many OpenAI-compatible servers
        kwargs["stream_options"] = {"include_usage": True}

        stream = await asyncio.wait_for(
            self._client.chat.completions.create(**kwargs),
            timeout=self._settings.openrouter_timeout_s,
        )

        usage_payload: dict[str, int] | None = None
        approx_out = 0
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                u = chunk.usage
                usage_payload = {
                    "prompt_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
                    "completion_tokens": int(getattr(u, "completion_tokens", 0) or 0),
                }
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            tok = getattr(delta, "content", None) or ""
            if tok:
                approx_out += max(1, len(tok) // 4)
                yield "token", tok

        if usage_payload is None:
            # Rough estimate if provider omitted usage on stream
            usage_payload = {"prompt_tokens": 0, "completion_tokens": approx_out}
        yield "usage", usage_payload
