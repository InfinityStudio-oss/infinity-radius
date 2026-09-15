"""System/ops endpoints: health checks. Reports the real, live status of
each dependency — never a fabricated "healthy" fallback. A dependency
that hasn't been configured yet reports "not_configured", not "ok"."""

from typing import Literal

import redis.asyncio as redis_asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter()

DependencyStatus = Literal["ok", "error", "not_configured"]


class DependencyHealth(BaseModel):
    status: DependencyStatus
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: DependencyHealth
    redis: DependencyHealth
    network_agent: DependencyHealth


async def _check_database() -> DependencyHealth:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return DependencyHealth(status="ok")
    except Exception as exc:  # noqa: BLE001 — health check must not raise
        return DependencyHealth(status="error", detail=str(exc))


async def _check_redis() -> DependencyHealth:
    settings = get_settings()
    client = redis_asyncio.from_url(str(settings.redis_url))  # type: ignore[no-untyped-call]
    try:
        await client.ping()
        return DependencyHealth(status="ok")
    except Exception as exc:  # noqa: BLE001
        return DependencyHealth(status="error", detail=str(exc))
    finally:
        await client.aclose()


def _check_network_agent() -> DependencyHealth:
    settings = get_settings()
    if not settings.network_agent_base_url:
        return DependencyHealth(
            status="not_configured", detail="NETWORK_AGENT_BASE_URL is not set"
        )
    # A live reachability check is added once the Network Agent's own health
    # contract is defined — see apps/network-agent.
    return DependencyHealth(status="not_configured", detail="Reachability check not implemented")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    database = await _check_database()
    redis_health = await _check_redis()
    network_agent = _check_network_agent()

    overall: Literal["ok", "degraded"] = (
        "ok" if database.status == "ok" and redis_health.status == "ok" else "degraded"
    )

    return HealthResponse(
        status=overall,
        database=database,
        redis=redis_health,
        network_agent=network_agent,
    )


@router.get("/health/database", response_model=DependencyHealth)
async def health_database() -> DependencyHealth:
    return await _check_database()


@router.get("/health/redis", response_model=DependencyHealth)
async def health_redis() -> DependencyHealth:
    return await _check_redis()
