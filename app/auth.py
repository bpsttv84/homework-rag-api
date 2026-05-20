"""X-API-Key authentication and tier metadata."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import Header, HTTPException, status

_CONFIG: dict[str, Any] | None = None


def load_api_keys_config() -> dict[str, Any]:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    path = Path(__file__).resolve().parent / "api_keys.yaml"
    with path.open(encoding="utf-8") as f:
        _CONFIG = yaml.safe_load(f)
    return _CONFIG


@dataclass(frozen=True)
class ApiKeyContext:
    raw_key: str
    tier: str
    tokens_per_minute: int
    models: list[str]


def resolve_api_key(x_api_key: str | None) -> ApiKeyContext:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    cfg = load_api_keys_config()
    keys = cfg.get("keys", {})
    entry = keys.get(x_api_key)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    models = list(entry.get("models") or [])
    if len(models) < 1:
        raise HTTPException(500, "API key misconfigured: no models")
    return ApiKeyContext(
        raw_key=x_api_key,
        tier=str(entry.get("tier", "unknown")),
        tokens_per_minute=int(entry.get("tokens_per_minute", 5000)),
        models=models,
    )


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> ApiKeyContext:
    return resolve_api_key(x_api_key)
