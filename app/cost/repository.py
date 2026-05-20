"""Persist LLM usage rows (SQLite or Postgres via DATABASE_URL)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, case, func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

metadata = MetaData()

llm_costs = Table(
    "llm_costs",
    metadata,
    Column("request_id", String(36), primary_key=True),
    Column("api_key", String(256), nullable=False),
    Column("model", String(128), nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("cost_usd", Float, nullable=False),
    Column("latency_ms", Float, nullable=False),
    Column("ttft_ms", Float, nullable=False),
    Column("cache_hit", Boolean, nullable=False),
    Column("fallback_used", Boolean, nullable=False),
    Column("output_filtered", Boolean, nullable=False, default=False),
    Column("tier", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, future=True)


async def init_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def insert_cost_row(
    conn: AsyncConnection,
    *,
    request_id: str,
    api_key: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: float,
    ttft_ms: float,
    cache_hit: bool,
    fallback_used: bool,
    output_filtered: bool,
    tier: str,
) -> None:
    await conn.execute(
        llm_costs.insert().values(
            request_id=request_id,
            api_key=api_key,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            cache_hit=cache_hit,
            fallback_used=fallback_used,
            output_filtered=output_filtered,
            tier=tier,
            created_at=datetime.now(timezone.utc),
        )
    )


async def usage_today(conn: AsyncConnection, api_key: str) -> dict[str, Any]:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    q = (
        select(
            func.count().label("requests"),
            func.coalesce(func.sum(llm_costs.c.input_tokens + llm_costs.c.output_tokens), 0).label("tokens"),
            func.coalesce(func.sum(llm_costs.c.cost_usd), 0.0).label("cost_usd"),
        )
        .where(llm_costs.c.api_key == api_key)
        .where(llm_costs.c.created_at >= start)
    )
    row = (await conn.execute(q)).one()
    return {
        "requests": int(row.requests),
        "tokens": int(row.tokens),
        "cost_usd": round(float(row.cost_usd), 4),
    }


async def usage_breakdown(conn: AsyncConnection, api_key: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    since = datetime.fromtimestamp(now.timestamp() - 3600, tz=timezone.utc)

    q_models = (
        select(
            llm_costs.c.model,
            func.count().label("n"),
            func.sum(llm_costs.c.input_tokens).label("in_tok"),
            func.sum(llm_costs.c.output_tokens).label("out_tok"),
            func.sum(llm_costs.c.cost_usd).label("cost"),
            func.avg(llm_costs.c.latency_ms).label("avg_lat"),
        )
        .where(llm_costs.c.api_key == api_key)
        .where(llm_costs.c.created_at >= since)
        .group_by(llm_costs.c.model)
    )
    rows = (await conn.execute(q_models)).all()

    q_hit = select(
        func.avg(case((llm_costs.c.cache_hit.is_(True), 1.0), else_=0.0)).label("cache_hit_rate"),
        func.avg(case((llm_costs.c.fallback_used.is_(True), 1.0), else_=0.0)).label("fallback_rate"),
        func.avg(llm_costs.c.latency_ms).label("avg_latency_ms"),
    ).where(llm_costs.c.api_key == api_key).where(llm_costs.c.created_at >= since)
    agg = (await conn.execute(q_hit)).one()

    models_out: list[dict[str, Any]] = []
    for r in rows:
        models_out.append(
            {
                "model": r.model,
                "requests": int(r.n),
                "input_tokens": int(r.in_tok or 0),
                "output_tokens": int(r.out_tok or 0),
                "cost_usd": round(float(r.cost or 0), 6),
                "avg_latency_ms": round(float(r.avg_lat or 0), 2),
            }
        )

    return {
        "window": "last_1h",
        "cache_hit_rate": round(float(agg.cache_hit_rate or 0), 4),
        "fallback_rate": round(float(agg.fallback_rate or 0), 4),
        "avg_latency_ms": round(float(agg.avg_latency_ms or 0), 2),
        "models": models_out,
    }
