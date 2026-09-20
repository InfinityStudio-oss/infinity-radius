"""Captive-portal-specific abuse controls.

The global middleware limiter (app/middleware/rate_limit.py) keys on client
IP, which is close to useless here: every customer behind one hotspot
shares a single public IP, so an IP limit tight enough to stop an attacker
would throttle a busy site's own paying customers, and one loose enough
not to would barely constrain an attacker on mobile data.

So this limits on dimensions that actually correspond to a person trying
to pay:

    session   one captive session is one customer's visit
    phone     the normalized msisdn an STK would be sent to — the thing a
              spammer would target someone else with
    router    a whole site, as a blast-radius ceiling, set far higher

Every limit is a fixed window in Redis, configurable, and FAILS OPEN: if
Redis is unreachable the payment is allowed through and a warning is
logged. A limiter that takes payments down when its cache hiccups is worse
than no limiter — the kill switch, the duplicate-attempt check and the
provider's own controls all still apply underneath.

These are Infinity Radius's own operational controls. Selcom publishes no
rate limits for Mobile Checkout, so none are invented here.
"""

from dataclasses import dataclass
from uuid import UUID

import redis.asyncio as redis_asyncio
import structlog

from app.core.config import get_settings

logger = structlog.get_logger("services.captive_rate_limit")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    # Which dimension rejected it — for the audit trail and for support,
    # never shown to the customer in a way that helps them tune around it.
    dimension: str | None = None


class CaptiveRateLimiter:
    """Fixed-window counters, one per dimension."""

    def __init__(self) -> None:
        self._client: redis_asyncio.Redis | None = None

    def _get_client(self) -> redis_asyncio.Redis:
        if self._client is None:
            self._client = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
                str(get_settings().redis_url)
            )
        return self._client

    async def _hit(self, *, key: str, limit: int, window: int) -> bool:
        """True if this hit is within the limit. Fails open on any Redis
        error."""
        try:
            client = self._get_client()
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, window)
            return bool(count <= limit)
        except Exception:  # noqa: BLE001 — never let Redis block a payment
            logger.warning("captive_rate_limit.backend_unavailable", exc_info=True)
            return True

    async def check(
        self, *, session_id: UUID, phone: str, router_id: UUID
    ) -> RateLimitDecision:
        """Checks every dimension. Evaluated narrowest-first so the
        reported dimension is the most specific one that tripped.

        `phone` must already be normalized (255XXXXXXXXX) so that
        0712345678 and +255712345678 cannot be used to get two budgets for
        the same handset.
        """
        settings = get_settings()
        window = settings.captive_rate_limit_window_seconds
        bucket = 0 if window <= 0 else int(__import__("time").time() // window)

        checks = (
            ("session", f"captive:rl:session:{session_id}:{bucket}",
             settings.captive_rate_limit_per_session),
            ("phone", f"captive:rl:phone:{phone}:{bucket}",
             settings.captive_rate_limit_per_phone),
            ("router", f"captive:rl:router:{router_id}:{bucket}",
             settings.captive_rate_limit_per_router),
        )
        for dimension, key, limit in checks:
            if limit <= 0:
                continue  # 0 or negative disables that dimension entirely
            if not await self._hit(key=key, limit=limit, window=window):
                logger.info(
                    "captive_rate_limit.rejected",
                    dimension=dimension,
                    # Never the raw msisdn in a log line.
                    router_id=str(router_id),
                )
                return RateLimitDecision(allowed=False, dimension=dimension)
        return RateLimitDecision(allowed=True)
