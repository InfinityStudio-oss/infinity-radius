"""Captive-portal rate limiting.

The dimensions matter more than the numbers. A hotspot NATs every customer
behind one public IP, so the global IP limiter cannot tell a busy site
from an attacker: tight enough to stop abuse would throttle a site's own
paying customers. These limits key on session, phone and router instead —
things that correspond to one person trying to pay.

Failing OPEN is deliberate and tested: if Redis is down, payments must
still work. A limiter that takes payments offline when its cache hiccups
is worse than no limiter, and the kill switch, duplicate-attempt guard and
provider controls all still apply underneath.
"""

import asyncio
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.services.captive_rate_limit import CaptiveRateLimiter


def _limiter() -> CaptiveRateLimiter:
    return CaptiveRateLimiter()


def test_allows_traffic_within_the_limit() -> None:
    limiter = _limiter()
    session_id, router_id = uuid4(), uuid4()
    phone = f"25575{uuid4().int % 10**7:07d}"

    async def _run() -> list[bool]:
        return [
            (await limiter.check(session_id=session_id, phone=phone, router_id=router_id)).allowed
            for _ in range(get_settings().captive_rate_limit_per_session)
        ]

    assert all(asyncio.run(_run()))


def test_rejects_once_the_session_budget_is_spent() -> None:
    limiter = _limiter()
    session_id, router_id = uuid4(), uuid4()
    phone = f"25575{uuid4().int % 10**7:07d}"
    limit = get_settings().captive_rate_limit_per_session

    async def _run() -> object:
        for _ in range(limit):
            await limiter.check(session_id=session_id, phone=phone, router_id=router_id)
        return await limiter.check(session_id=session_id, phone=phone, router_id=router_id)

    decision = asyncio.run(_run())
    assert decision.allowed is False
    assert decision.dimension == "session"


def test_phone_budget_is_independent_of_session() -> None:
    """The dimension that actually protects a third party: someone must not
    be able to open fresh sessions to keep pushing STK prompts at a number
    that is not theirs."""
    limiter = _limiter()
    router_id = uuid4()
    phone = f"25575{uuid4().int % 10**7:07d}"
    limit = get_settings().captive_rate_limit_per_phone

    async def _run() -> object:
        # A brand-new session each time, so the session budget never trips.
        for _ in range(limit):
            await limiter.check(session_id=uuid4(), phone=phone, router_id=router_id)
        return await limiter.check(session_id=uuid4(), phone=phone, router_id=router_id)

    decision = asyncio.run(_run())
    assert decision.allowed is False
    assert decision.dimension == "phone"


def test_separate_phones_do_not_share_a_budget() -> None:
    """One customer exhausting their attempts must not lock out everyone
    else at the same site — the exact failure an IP-only limiter causes."""
    limiter = _limiter()
    router_id = uuid4()
    busy = f"25575{uuid4().int % 10**7:07d}"
    other = f"25575{uuid4().int % 10**7:07d}"

    async def _run() -> object:
        for _ in range(get_settings().captive_rate_limit_per_phone + 2):
            await limiter.check(session_id=uuid4(), phone=busy, router_id=router_id)
        return await limiter.check(session_id=uuid4(), phone=other, router_id=router_id)

    assert asyncio.run(_run()).allowed is True


def test_fails_open_when_redis_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis down must never mean payments down."""
    limiter = _limiter()

    def _broken() -> object:
        raise ConnectionError("redis is gone")

    monkeypatch.setattr(limiter, "_get_client", _broken)

    async def _run() -> object:
        return await limiter.check(
            session_id=uuid4(), phone="255755000000", router_id=uuid4()
        )

    assert asyncio.run(_run()).allowed is True


def test_a_zero_limit_disables_that_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    """Operators need an escape hatch that does not require a code change."""
    monkeypatch.setenv("CAPTIVE_RATE_LIMIT_PER_SESSION", "0")
    get_settings.cache_clear()
    try:
        limiter = _limiter()
        session_id, router_id = uuid4(), uuid4()

        async def _run() -> list[bool]:
            # A fresh phone each call so ONLY the session dimension is under
            # test — the phone budget is still enforced and would otherwise
            # trip first, which is itself the correct behaviour.
            return [
                (
                    await limiter.check(
                        session_id=session_id,
                        phone=f"25575{uuid4().int % 10**7:07d}",
                        router_id=router_id,
                    )
                ).allowed
                for _ in range(10)
            ]

        # Far past the normal session budget, yet all allowed.
        assert all(asyncio.run(_run()))
    finally:
        get_settings.cache_clear()
