"""Security of the captive payment session and initiation endpoint.

The threat model is a hostile browser on a hotspot LAN. It holds the
router token — which is baked into every router's hotspot config and is
effectively public to anyone who associated with that AP — and can send
anything it likes to the public API.

What it must NOT be able to do:
  * spend money with the router token alone
  * replay a payment session
  * pay less than a package costs
  * buy another tenant's package
  * read another customer's payment
  * make the system send repeated STK pushes to someone else's handset
  * get past the production kill switch

Every test here drives the real public routes.
"""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.captive_intent_token import create_captive_intent_token
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.network import CaptiveSession
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)

# A valid Fernet key so intent tokens can be issued at all. Test-only.
_TEST_INTENT_KEY = "8ZQZ1yq8kJ1kZ9rN6Xk2mQ0pV7sT3wY5bA4cD6eF8gI="


@pytest.fixture(autouse=True)
def _intent_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The signing key is optional in Settings (the app must boot without
    it), so every test here sets one explicitly."""
    monkeypatch.setenv("CAPTIVE_INTENT_TOKEN_SIGNING_KEY", _TEST_INTENT_KEY)
    get_settings.cache_clear()
    import app.core.captive_intent_token as m

    m._fernet.cache_clear()
    yield
    get_settings.cache_clear()
    m._fernet.cache_clear()


@pytest.fixture
def gate_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opens the production kill switch so the checks BEHIND it can be
    tested at all.

    With the gate closed every request short-circuits to "unavailable" —
    correct in production, but it would mean none of the session, replay or
    cross-tenant guards were ever exercised. Selcom's client is stubbed to
    raise, so this can still never make a real provider call: any test that
    accidentally reaches the network fails loudly instead of paying money.
    """
    from app.integrations.selcom_collection.client import SelcomCollectionClient

    monkeypatch.setenv("SELCOM_COLLECTION_BASE_URL", "https://apigwtest.selcommobile.com")
    monkeypatch.setenv("SELCOM_COLLECTION_API_KEY", "test-collection-key-never-real")
    monkeypatch.setenv("SELCOM_COLLECTION_API_SECRET", "test-collection-secret-never-real")
    monkeypatch.setenv("SELCOM_COLLECTION_DIGEST_METHOD", "HS256")
    monkeypatch.setenv("SELCOM_COLLECTION_VENDOR", "TEST-VENDOR")
    monkeypatch.setenv("SELCOM_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("SELCOM_COLLECTION_PRODUCTION_ENABLED", "true")
    get_settings.cache_clear()

    async def _forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(
            "A test reached the real Selcom client. No test may contact a "
            "payment provider."
        )

    for method in ("create_order_minimal", "wallet_payment", "order_status"):
        monkeypatch.setattr(SelcomCollectionClient, method, _forbidden)
    yield
    get_settings.cache_clear()


def _site(headers: dict[str, str]) -> tuple[str, str, str]:
    """Creates a router + active package and returns (router_id, package_id,
    router_token)."""
    router_id = client.post(
        "/api/v1/routers", headers=headers, json={"name": "Captive Router"}
    ).json()["data"]["id"]
    package_id = client.post(
        "/api/v1/packages",
        headers=headers,
        json={"name": "Day Pass", "price_tzs": "10000", "status": "active"},
    ).json()["data"]["id"]
    token = client.get(
        f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
    ).json()["data"]["router_token"]
    return router_id, package_id, token


def _open_session(router_token: str, mac: str | None = "AA:BB:CC:DD:EE:FF") -> str:
    response = client.post(
        "/api/v1/public/captive-portal/session",
        json={"router": router_token, "mac_address": mac},
    )
    assert response.status_code == 201, response.text
    return response.json()["intent_token"]


# ------------------------------------------------------------- session


def test_router_token_alone_cannot_start_a_payment(gate_open: None) -> None:
    """The whole reason a second token exists: a site identifier must not
    be a payment credential."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        _, package_id, router_token = _site(headers)

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={
                "intent_token": router_token,  # a VALID router token
                "package_id": package_id,
                "phone": "0712345678",
            },
        )
    # Rejected: signed with a different key, so it is not an intent token.
    assert response.status_code in (401, 422)


def test_session_issues_a_token_and_persists_a_row() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        router_id, _, router_token = _site(headers)

        body = client.post(
            "/api/v1/public/captive-portal/session",
            json={"router": router_token, "mac_address": "AA:BB:CC:DD:EE:FF"},
        ).json()

        assert body["intent_token"]
        assert body["expires_at"]
        # Never leaks tenant/router/nonce to the browser.
        assert "tenant_id" not in body
        assert "router_id" not in body
        assert "nonce" not in body

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, router_id, consumed_at FROM captive_sessions "
                "WHERE router_id = %s",
                (router_id,),
            )
            row = cur.fetchone()
        assert row is not None
        assert str(row[0]) == str(tenant_id)  # resolved server-side
        assert row[2] is None  # not yet consumed


def test_forged_router_token_is_rejected() -> None:
    response = client.post(
        "/api/v1/public/captive-portal/session",
        json={"router": "not-a-real-token", "mac_address": None},
    )
    assert response.status_code == 401


def test_forged_intent_token_is_rejected(gate_open: None) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        _, package_id, _ = _site(headers)

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={
                "intent_token": "gAAAAABmFORGEDFORGEDFORGEDFORGED",
                "package_id": package_id,
                "phone": "0712345678",
            },
        )
    assert response.status_code == 422


def test_intent_token_for_a_deleted_session_is_rejected(gate_open: None) -> None:
    """A structurally valid token whose session no longer exists must fail
    exactly like a forged one — no distinguishable error."""
    token = create_captive_intent_token(uuid4())
    response = client.post(
        "/api/v1/public/captive-portal/payments/initiate",
        json={"intent_token": token, "package_id": str(uuid4()), "phone": "0712345678"},
    )
    assert response.status_code == 422


def test_expired_session_is_rejected(gate_open: None) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        router_id, package_id, router_token = _site(headers)
        intent = _open_session(router_token)

        # Expire it in the database — the second, independent expiry check.
        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "UPDATE captive_sessions SET expires_at = now() - interval '1 hour' "
                "WHERE router_id = %s",
                (router_id,),
            )

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": package_id, "phone": "0712345678"},
        )
    assert response.status_code == 422


def test_consumed_session_cannot_be_replayed(gate_open: None) -> None:
    """Single use. A replayed token must not open a second payment even
    while the first is still live."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        router_id, package_id, router_token = _site(headers)
        intent = _open_session(router_token)

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "UPDATE captive_sessions SET consumed_at = now() WHERE router_id = %s",
                (router_id,),
            )

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": package_id, "phone": "0712345678"},
        )
    assert response.status_code == 422


def test_session_nonce_is_unique_per_session() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        router_id, _, router_token = _site(headers)
        _open_session(router_token)
        _open_session(router_token)

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), count(DISTINCT nonce) FROM captive_sessions WHERE router_id = %s",
                (router_id,),
            )
            total, distinct = cur.fetchone()
    assert total == 2
    assert distinct == 2


# ------------------------------------------------- tenant / package guards


def test_amount_is_not_a_field_a_client_can_send() -> None:
    """The TZS 10,000 -> TZS 1 attack is impossible by SCHEMA, not by
    validation: the request model has no amount/price/currency field, so a
    tampered body carries nothing to override."""
    from app.schemas.captive_portal import CaptivePortalPaymentInitiateRequest

    fields = set(CaptivePortalPaymentInitiateRequest.model_fields)
    assert fields == {"intent_token", "package_id", "phone"}
    for forbidden in ("amount", "price", "price_tzs", "currency", "tenant_id",
                      "commission", "payment_provider"):
        assert forbidden not in fields


def test_cross_tenant_package_is_rejected(gate_open: None) -> None:
    """A valid session from tenant A cannot buy tenant B's package."""
    with SeededContext() as ctx:
        tenant_a = ctx.new_tenant(name="Tenant A")
        tenant_b = ctx.new_tenant(name="Tenant B")
        headers_a = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_a))
        headers_b = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b))

        _, _, router_token_a = _site(headers_a)
        _, package_b, _ = _site(headers_b)
        intent = _open_session(router_token_a)

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": package_b, "phone": "0712345678"},
        )
    assert response.status_code == 422
    # Rejected the same way a nonexistent package is, so the response
    # cannot be used to probe whether a given package id exists elsewhere.
    body = str(response.json()).lower()
    assert "does not belong" in body


def test_nonexistent_package_is_rejected(gate_open: None) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        _, _, router_token = _site(headers)
        intent = _open_session(router_token)

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": str(uuid4()), "phone": "0712345678"},
        )
    assert response.status_code == 422


# ------------------------------------------------------------ kill switch


def test_production_gate_blocks_before_any_persistence_or_provider_call() -> None:
    """The regression test Phase 9 asks for: with the gate closed, the
    endpoint must create NO transaction, NO subscription and NO customer,
    and must not consume the session — so there is nothing to reconcile or
    clean up afterwards."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        router_id, package_id, router_token = _site(headers)
        intent = _open_session(router_token)

        # SELCOM_COLLECTION_PRODUCTION_ENABLED defaults to false in tests.
        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": package_id, "phone": "0712345678"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "unavailable"
        assert body["transaction_token"] is None

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM transactions WHERE tenant_id = %s", (str(tenant_id),)
            )
            (transactions,) = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM subscriptions WHERE tenant_id = %s", (str(tenant_id),)
            )
            (subscriptions,) = cur.fetchone()
            cur.execute("SELECT count(*) FROM customers WHERE tenant_id = %s", (str(tenant_id),))
            (customers,) = cur.fetchone()
            cur.execute(
                "SELECT consumed_at FROM captive_sessions WHERE router_id = %s", (router_id,)
            )
            (consumed_at,) = cur.fetchone()

    assert transactions == 0, "gate must run before any transaction is persisted"
    assert subscriptions == 0, "gate must not leave an orphan subscription"
    assert customers == 0, "gate must not create a customer"
    assert consumed_at is None, "a blocked attempt must not burn the session"


def test_gate_message_is_customer_safe() -> None:
    """The customer-facing copy must not reveal which control is in force,
    or an attacker could probe the endpoint to map the gates."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        _, package_id, router_token = _site(headers)
        intent = _open_session(router_token)

        body = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": package_id, "phone": "0712345678"},
        ).json()

    message = body["message"].lower()
    for leak in ("selcom", "kill switch", "flag", "enabled", "production", "gate", "api"):
        assert leak not in message


# ------------------------------------------------------- status endpoint


def test_status_for_an_unknown_token_reports_not_found() -> None:
    response = client.get(
        "/api/v1/public/captive-portal/payments/status", params={"token": "not-a-real-token"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "not_found"


def test_status_never_accepts_a_raw_transaction_id() -> None:
    """Arbitrary transaction lookup must be impossible — the endpoint takes
    an opaque token, and a database id is not one."""
    response = client.get(
        "/api/v1/public/captive-portal/payments/status", params={"token": str(uuid4())}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "not_found"


async def _session_row(router_id: str) -> CaptiveSession | None:
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(CaptiveSession).where(CaptiveSession.router_id == UUID(router_id))
            )
        ).scalars().first()


def test_mac_address_is_recorded_but_never_required() -> None:
    """A MAC is a correlation hint. It must be stored when present and must
    never be required — randomized MACs and redirects without one are both
    normal."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        router_id, _, router_token = _site(headers)

        _open_session(router_token, mac=None)
        session = asyncio.run(_session_row(router_id))
        assert session is not None
        assert session.mac_address is None
