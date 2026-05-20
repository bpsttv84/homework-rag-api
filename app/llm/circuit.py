"""Simple circuit breaker for primary model (per tier+model key)."""
from __future__ import annotations

import time
from collections import deque

_window_s = 60
_threshold = 5
_open_s = 60

_failures: dict[str, deque[float]] = {}
_open_until: dict[str, float] = {}


def breaker_key(tier: str, primary_model: str) -> str:
    return f"{tier}::{primary_model}"


def should_skip_primary(tier: str, primary_model: str) -> bool:
    key = breaker_key(tier, primary_model)
    until = _open_until.get(key, 0.0)
    return time.time() < until


def record_failure(tier: str, primary_model: str) -> None:
    key = breaker_key(tier, primary_model)
    now = time.time()
    dq = _failures.setdefault(key, deque())
    dq.append(now)
    while dq and now - dq[0] > _window_s:
        dq.popleft()
    if len(dq) >= _threshold:
        _open_until[key] = now + _open_s


def record_success(tier: str, primary_model: str) -> None:
    key = breaker_key(tier, primary_model)
    _failures.pop(key, None)
    _open_until.pop(key, None)
