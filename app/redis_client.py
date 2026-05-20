"""Redis connection (local docker or Upstash with TLS)."""
from __future__ import annotations

import ssl

import redis.asyncio as aioredis


def create_redis(url: str) -> aioredis.Redis:
    """Upstash needs rediss:// + relaxed TLS on some Windows/Python builds."""
    kwargs: dict = {"decode_responses": True}
    if url.startswith("rediss://"):
        kwargs["ssl_cert_reqs"] = ssl.CERT_NONE
    return aioredis.from_url(url, **kwargs)
