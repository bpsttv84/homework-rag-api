"""Token-bucket rate limiting in Redis (no Lua) + per-key asyncio lock."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as redis

_locks: dict[str, asyncio.Lock] = {}


def _key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:24]


def _lock_for(api_key: str) -> asyncio.Lock:
    h = _key_hash(api_key)
    if h not in _locks:
        _locks[h] = asyncio.Lock()
    return _locks[h]


def _redis_key(api_key: str) -> str:
    return f"rl:{_key_hash(api_key)}"


async def _read_state(r: "redis.Redis", api_key: str, capacity: float) -> tuple[float, float]:
    raw = await r.get(_redis_key(api_key))
    if not raw:
        # Fresh bucket starts full (token bucket semantics).
        return float(capacity), time.time()
    data = json.loads(raw)
    return float(data.get("balance", 0.0)), float(data.get("ts", time.time()))


async def _write_state(r: "redis.Redis", api_key: str, balance: float, ts: float) -> None:
    payload = json.dumps({"balance": balance, "ts": ts})
    await r.set(_redis_key(api_key), payload, ex=86400)


def _refill(balance: float, ts: float, now: float, capacity: float) -> tuple[float, float]:
    """Refill tokens linearly: full bucket restores over 60s."""
    rate_per_sec = capacity / 60.0
    dt = max(0.0, now - ts)
    added = dt * rate_per_sec
    nb = min(capacity, balance + added)
    return nb, now


async def precheck_or_raise(r: "redis.Redis", api_key: str, capacity: float, estimate_tokens: int) -> None:
    """Raise HTTPException 429 if estimated tokens cannot be served."""
    from fastapi import HTTPException, status

    lock = _lock_for(api_key)
    async with lock:
        now = time.time()
        bal, ts = await _read_state(r, api_key, capacity)
        bal, ts = _refill(bal, ts, now, capacity)
        if bal < estimate_tokens:
            rate_per_sec = capacity / 60.0
            deficit = estimate_tokens - bal
            retry_after = max(1, int(math.ceil(deficit / rate_per_sec)))
            await _write_state(r, api_key, bal, ts)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Token bucket exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        # optional: reserve by subtracting estimate now to reduce bursts — homework deducts after;
        # we only check headroom here.
        await _write_state(r, api_key, bal, ts)


async def consume_tokens(r: "redis.Redis", api_key: str, capacity: float, tokens: int) -> None:
    lock = _lock_for(api_key)
    async with lock:
        now = time.time()
        bal, ts = await _read_state(r, api_key, capacity)
        bal, ts = _refill(bal, ts, now, capacity)
        bal = max(0.0, bal - float(tokens))
        await _write_state(r, api_key, bal, ts)
