"""The captive portal's payment flow: initiate -> poll (pending) ->
[payment confirmation, simulated here by calling
CaptivePortalService.mark_transaction_completed directly, since no
payment provider is wired up to captive-portal payments yet — see
app/services/captive_portal.py's module docstring] -> poll (completed,
with RADIUS login credentials) -> real RADIUS rows and a real wallet
ledger credit exist.
"""

import asyncio
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.transaction_token import resolve_transaction_token
from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.captive_activation import run_activation
from app.services.captive_portal import CaptivePortalService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def _radius_dsn() -> str:
    url = str(get_settings().radius_database_url)
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    return (
        f"host={parsed.hostname} port={parsed.port or 5432} "
        f"dbname={parsed.path.lstrip('/')} user={parsed.username} "
        f"password={parsed.password}"
    )


def _cleanup_radius(*, username: str, package_id: str) -> None:
    conn = psycopg.connect(_radius_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM radcheck WHERE username = %s", (username,))
        cur.execute("DELETE FROM radusergroup WHERE username = %s", (username,))
        cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (f"pkg_{package_id}",))
        cur.execute("DELETE FROM radgroupcheck WHERE groupname = %s", (f"pkg_{package_id}",))
    conn.close()


async def _pay_and_activate(transaction_id: UUID) -> None:
    """Stands in for the payment provider that captive-portal payments are
    not yet wired to — see this file's module docstring.

    Runs the two steps the way production will: the payment is finalized
    and COMMITTED first, then activation runs in its own transaction via
    run_activation(). They are deliberately never in the same transaction
    (see app/services/captive_activation.py)."""
    async with AsyncSessionLocal() as db:
        await CaptivePortalService(db).finalize_payment(transaction_id=transaction_id)
        await db.commit()
    await run_activation(transaction_id=transaction_id)


def _create_router_and_package(headers: dict[str, str]) -> tuple[str, str]:
    router_response = client.post(
        "/api/v1/routers", headers=headers, json={"name": "Captive Portal Test Router"}
    )
    router_id = router_response.json()["data"]["id"]

    package_response = client.post(
        "/api/v1/packages",
        headers=headers,
        json={
            "name": "Daily 1GB",
            "price_tzs": "1500",
            "duration_minutes": 1440,
            "download_speed_kbps": 2048,
            "upload_speed_kbps": 1024,
            "simultaneous_sessions": 1,
            "activation_type": "immediate",
            "status": "active",
        },
    )
    package_id = package_response.json()["data"]["id"]
    return router_id, package_id


_TEST_INTENT_KEY = "8ZQZ1yq8kJ1kZ9rN6Xk2mQ0pV7sT3wY5bA4cD6eF8gI="


@pytest.fixture(autouse=True)
def _intent_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CAPTIVE_INTENT_TOKEN_SIGNING_KEY", _TEST_INTENT_KEY)
    get_settings.cache_clear()
    import app.core.captive_intent_token as m

    m._fernet.cache_clear()
    yield
    get_settings.cache_clear()
    m._fernet.cache_clear()


@pytest.fixture
def gate_open(monkeypatch: pytest.MonkeyPatch):
    """Opens the production gate and stubs Selcom so the flow behind the
    kill switch can be exercised without any possibility of a real
    provider call."""
    from app.integrations.selcom_collection.client import SelcomCollectionClient

    monkeypatch.setenv("SELCOM_COLLECTION_BASE_URL", "https://apigwtest.selcommobile.com")
    monkeypatch.setenv("SELCOM_COLLECTION_API_KEY", "test-collection-key-never-real")
    monkeypatch.setenv("SELCOM_COLLECTION_API_SECRET", "test-collection-secret-never-real")
    monkeypatch.setenv("SELCOM_COLLECTION_DIGEST_METHOD", "HS256")
    monkeypatch.setenv("SELCOM_COLLECTION_VENDOR", "TEST-VENDOR")
    monkeypatch.setenv("SELCOM_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("SELCOM_COLLECTION_PRODUCTION_ENABLED", "true")
    get_settings.cache_clear()

    async def _create_order(self, **kwargs):
        return None

    async def _wallet_payment(self, **kwargs):
        return SimpleNamespace(resultcode="111", message="PENDING")

    monkeypatch.setattr(SelcomCollectionClient, "create_order_minimal", _create_order)
    monkeypatch.setattr(SelcomCollectionClient, "wallet_payment", _wallet_payment)
    yield
    get_settings.cache_clear()


def _open_session(router_token: str, mac: str | None = "AA:BB:CC:DD:EE:FF") -> str:
    response = client.post(
        "/api/v1/public/captive-portal/session",
        json={"router": router_token, "mac_address": mac},
    )
    assert response.status_code == 201, response.text
    return response.json()["intent_token"]


def test_initiate_payment_persists_the_full_captive_context(gate_open: None) -> None:
    """Every column support needs to answer "who paid what, from where"
    must be written at initiation — not inferred later from a join that
    breaks when a payment never completes."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        router_id, package_id = _create_router_and_package(headers)
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]
        intent = _open_session(router_token)

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": package_id, "phone": "0755900001"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "pending", body
        # The authoritative amount came from the package, not the request.
        assert body["amount"] == "1500.00"
        assert body["currency"] == "TZS"
        assert body["transaction_token"]

        transaction_id = resolve_transaction_token(body["transaction_token"])
        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT transaction_type, payment_provider, package_id, router_id, "
                "captive_session_id, device_mac, payer_phone, amount, currency, status "
                "FROM transactions WHERE id = %s",
                (str(transaction_id),),
            )
            row = cur.fetchone()

    assert row is not None
    (
        transaction_type, payment_provider, pkg, rtr, session_id,
        device_mac, payer_phone, amount, currency, status,
    ) = row
    # The pairing that makes two columns necessary.
    assert transaction_type == "CAPTIVE_PORTAL"
    assert payment_provider == "SELCOM_COLLECTION"
    assert str(pkg) == package_id
    assert str(rtr) == router_id
    assert session_id is not None
    assert device_mac == "AA:BB:CC:DD:EE:FF"
    # Normalized server-side from 0712345678.
    assert payer_phone == "255755900001"
    assert str(amount) == "1500.00"
    assert currency == "TZS"
    assert status == "STK_SENT"


def test_phone_is_normalized_server_side(gate_open: None) -> None:
    """All three accepted forms must converge on one stored msisdn, or the
    duplicate-attempt guard could be bypassed by changing the spelling."""
    for entered, expected in (
        ("0755000001", "255755000001"),
        ("+255755000002", "255755000002"),
        ("255755000003", "255755000003"),
    ):
        with SeededContext() as ctx:
            tenant_id = ctx.new_tenant()
            headers = auth_header(
                user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
            )
            router_id, package_id = _create_router_and_package(headers)
            router_token = client.get(
                f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
            ).json()["data"]["router_token"]
            intent = _open_session(router_token)

            response = client.post(
                "/api/v1/public/captive-portal/payments/initiate",
                json={"intent_token": intent, "package_id": package_id, "phone": entered},
            )
            body = response.json()
            assert body["status"] == "pending", body
            transaction_id = resolve_transaction_token(body["transaction_token"])
            assert ctx._conn is not None
            with ctx._conn.cursor() as cur:
                cur.execute(
                    "SELECT payer_phone FROM transactions WHERE id = %s", (str(transaction_id),)
                )
                (stored,) = cur.fetchone()
        assert stored == expected, f"{entered} normalized to {stored}"


def test_duplicate_submit_reuses_the_attempt_and_sends_no_second_stk(
    gate_open: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Double-click, refresh, second tab and HTTP retry all land here. The
    customer must get their ORIGINAL attempt back — a second STK to their
    handset would be both confusing and abusable."""
    from app.integrations.selcom_collection.client import SelcomCollectionClient

    stk_calls = {"n": 0}

    async def _counting_wallet_payment(self, **kwargs):
        stk_calls["n"] += 1
        return SimpleNamespace(resultcode="111", message="PENDING")

    monkeypatch.setattr(SelcomCollectionClient, "wallet_payment", _counting_wallet_payment)

    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        router_id, package_id = _create_router_and_package(headers)
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]
        intent = _open_session(router_token)
        payload = {"intent_token": intent, "package_id": package_id, "phone": "0755111222"}

        first = client.post("/api/v1/public/captive-portal/payments/initiate", json=payload)
        assert first.json()["status"] == "pending"

        # The session is single-use, so a replay is rejected outright...
        second = client.post("/api/v1/public/captive-portal/payments/initiate", json=payload)

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM transactions WHERE tenant_id = %s", (str(tenant_id),)
            )
            (transactions,) = cur.fetchone()

    # ...and either way there is exactly one attempt and exactly one STK.
    assert second.status_code in (201, 422)
    assert transactions == 1, "a duplicate submit must not create a second transaction"
    assert stk_calls["n"] == 1, "a duplicate submit must not trigger a second STK"


def test_initiate_payment_rejects_an_inactive_package(gate_open: None) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        router_id = client.post(
            "/api/v1/routers", headers=headers, json={"name": "Router"}
        ).json()["data"]["id"]
        package_id = client.post(
            "/api/v1/packages",
            headers=headers,
            json={"name": "Retired", "price_tzs": "500", "status": "archived"},
        ).json()["data"]["id"]
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]
        intent = _open_session(router_token)

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": package_id, "phone": "0755900009"},
        )
    assert response.status_code == 422


def test_initiate_payment_rejects_an_invalid_phone(gate_open: None) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        headers = auth_header(user_id=ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id))
        router_id, package_id = _create_router_and_package(headers)
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]
        intent = _open_session(router_token)

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": package_id, "phone": "12345"},
        )
    assert response.status_code == 422


def test_full_payment_flow_reaches_completed_with_radius_credentials(gate_open: None) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        router_id, package_id = _create_router_and_package(headers)
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]

        intent = _open_session(router_token)
        initiate_response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"intent_token": intent, "package_id": package_id, "phone": "0712345671"},
        )
        transaction_token = initiate_response.json()["transaction_token"]

        pending_status = client.get(
            "/api/v1/public/captive-portal/payments/status", params={"token": transaction_token}
        )
        assert pending_status.json()["status"] == "pending"

        transaction_id = resolve_transaction_token(transaction_token)
        assert transaction_id is not None

        try:
            # Stands in for the Selcom webhook this codebase can't
            # implement yet (see app/services/captive_portal.py's module
            # docstring) — drives the real finalize-then-activate path
            # directly. Must run before SeededContext's teardown
            # (which cascades-deletes the tenant this transaction belongs
            # to), so it stays inside this `with` block.
            asyncio.run(_pay_and_activate(transaction_id))

            completed_status = client.get(
                "/api/v1/public/captive-portal/payments/status",
                params={"token": transaction_token},
            )
            body = completed_status.json()
            assert body["status"] == "completed"
            assert body["login_username"] == "255712345671"
            assert body["login_password"]

            # Real RADIUS rows exist — not just an in-memory success flag.
            conn = psycopg.connect(_radius_dsn())
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM radcheck WHERE username = %s "
                    "AND attribute = 'Cleartext-Password'",
                    ("255712345671",),
                )
                password_row = cur.fetchone()
                assert password_row is not None
                (stored_password,) = password_row
            conn.close()
            assert stored_password == body["login_password"]

            # The tenant's wallet was really credited — gross 1500.00 split
            # via the tenant's 10% commercial terms into a 150.00 platform
            # fee and a 1350.00 tenant share, landing in `pending` (not yet
            # settled to `available`) — real ledger entries, not just a
            # transaction-status flip.
            wallet_response = client.get("/api/v1/wallet", headers=headers)
            wallet_data = wallet_response.json()["data"]
            assert wallet_data["pending_balance_tzs"] == "1350.00"
            assert wallet_data["available_balance_tzs"] == "0.00"

            ledger_response = client.get("/api/v1/wallet/ledger", headers=headers)
            ledger_items = ledger_response.json()["data"]
            assert len(ledger_items) == 3
            entries_by_type = {item["entry_type"]: item for item in ledger_items}
            assert entries_by_type["COLLECTION"]["amount"] == "1500.00"
            assert entries_by_type["PLATFORM_FEE"]["amount"] == "150.00"
            tenant_share_entry = entries_by_type["TENANT_SHARE"]
            assert tenant_share_entry["amount"] == "1350.00"
            assert tenant_share_entry["wallet_bucket"] == "pending"
            assert tenant_share_entry["reference_id"] == str(transaction_id)
        finally:
            _cleanup_radius(username="255712345671", package_id=package_id)
