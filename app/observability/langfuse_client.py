"""Optional Langfuse tracing (disabled when keys unset). Compatible with Langfuse Python SDK 4.x."""
from __future__ import annotations

from typing import Any

from app.config import Settings


def make_client(settings: Settings) -> Any | None:
    if not settings.langfuse_enabled:
        return None
    from langfuse import Langfuse

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


def start_trace(
    client: Any | None,
    *,
    name: str,
    input_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """SDK 4.x: root observation as span (replaces removed client.trace(...))."""
    if client is None:
        return None
    return client.start_observation(
        name=name,
        as_type="span",
        input=input_data or {},
        metadata=metadata or {},
    )


def span(parent: Any, name: str) -> Any:
    return parent.start_observation(name=name, as_type="span")


def finish_observation(
    obs: Any,
    *,
    output: Any = None,
    usage_details: dict[str, int] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Update then end (SDK 4 end() no longer accepts output)."""
    kw: dict[str, Any] = {}
    if output is not None:
        kw["output"] = output
    if usage_details is not None:
        kw["usage_details"] = usage_details
    if metadata is not None:
        kw["metadata"] = metadata
    if kw:
        obs.update(**kw)
    obs.end()


def generation(parent: Any, *, name: str, model: str, input: Any) -> Any:
    return parent.start_observation(
        name=name,
        as_type="generation",
        model=model,
        input=input,
    )
