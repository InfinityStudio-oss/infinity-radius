"""The captive portal's payment flow: initiate -> poll (pending) ->
[payment confirmation, simulated here by calling
CaptivePortalService.mark_transaction_completed directly rather than via
POST /api/v1/webhooks/selcom/collection — see test_selcom_webhook.py for
the real end-to-end webhook route, and app/services/captive_portal.py's
module docstring for why the webhook can't yet verify anything for real]
-> poll (completed, with RADIUS login credentials) -> real RADIUS rows
and a real wallet ledger credit exist.
"""

import asyncio
from urllib.parse import urlparse
from uuid import UUID

import psycopg
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.transaction_token import resolve_transaction_token
from app.db.session import AsyncSessionLocal
from app.main import app
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


async def _mark_completed_directly(transaction_id: UUID) -> None:
    """Stands in for the (not-yet-buildable) Selcom webhook — see this
    file's module docstring."""
    async with AsyncSessionLocal() as db:
        await CaptivePortalService(db).mark_transaction_completed(transaction_id=transaction_id)
        await db.commit()


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


def test_initiate_payment_creates_pending_transaction_and_subscription() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        router_id = client.post(
            "/api/v1/routers", headers=headers, json={"name": "Router"}
        ).json()["data"]["id"]
        package_id = client.post(
            "/api/v1/packages",
            headers=headers,
            json={"name": "Pkg", "price_tzs": "1500", "status": "active"},
        ).json()["data"]["id"]

        token_response = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        )
        router_token = token_response.json()["data"]["router_token"]

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"router": router_token, "package_id": package_id, "phone": "0712345678"},
        )

    assert response.status_code == 201
    body = response.json()  # public endpoint — no ApiResponse envelope
    assert body["status"] == "provider_not_configured"  # Selcom is not implemented
    assert body["amount"] == "1500.00"
    assert body["currency"] == "TZS"
    assert "transaction_token" in body
    # Never a raw database id anywhere in the response.
    assert "id" not in body
    assert "transaction_id" not in body
    assert "subscription_id" not in body
    assert "customer_id" not in body


def test_initiate_payment_writes_the_captive_portal_discriminator() -> None:
    """`transactions` is shared with Selcom Collection, so every captive
    portal row must classify itself explicitly — otherwise it would either
    be invisible or, worse, show up in a tenant's Collections list."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        router_id = client.post(
            "/api/v1/routers", headers=headers, json={"name": "Router"}
        ).json()["data"]["id"]
        package_id = client.post(
            "/api/v1/packages",
            headers=headers,
            json={"name": "Pkg", "price_tzs": "1500", "status": "active"},
        ).json()["data"]["id"]
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]

        initiate_response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"router": router_token, "package_id": package_id, "phone": "0712345678"},
        )
        transaction_id = resolve_transaction_token(
            initiate_response.json()["transaction_token"]
        )

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT transaction_type FROM transactions WHERE id = %s",
                (str(transaction_id),),
            )
            row = cur.fetchone()

    assert row is not None
    assert row[0] == "CAPTIVE_PORTAL"


def test_initiate_payment_records_mac_address_in_the_audit_trail() -> None:
    """mac_address correlates the payment with the originating hotspot
    session for audit/troubleshooting only — it must never affect the
    charged amount (already covered above: amount always == package
    price_tzs), but it should genuinely be recorded somewhere real."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        router_id, package_id = _create_router_and_package(headers)
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={
                "router": router_token,
                "package_id": package_id,
                "phone": "0712345699",
                "mac_address": "AA:BB:CC:DD:EE:FF",
            },
        )
        assert response.status_code == 201

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                'SELECT "metadata" FROM audit_logs WHERE action = %s '
                "ORDER BY created_at DESC LIMIT 1",
                ("captive_portal.payment_initiated",),
            )
            row = cur.fetchone()

    assert row is not None
    assert row[0]["mac_address"] == "AA:BB:CC:DD:EE:FF"


def test_initiate_payment_rejects_an_inactive_package() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        router_id = client.post(
            "/api/v1/routers", headers=headers, json={"name": "Router"}
        ).json()["data"]["id"]
        package_id = client.post(
            "/api/v1/packages",
            headers=headers,
            json={"name": "Archived Pkg", "price_tzs": "1500", "status": "archived"},
        ).json()["data"]["id"]
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"router": router_token, "package_id": package_id, "phone": "0712345678"},
        )

    assert response.status_code == 422


def test_initiate_payment_rejects_an_invalid_phone() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        router_id, package_id = _create_router_and_package(headers)
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]

        response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"router": router_token, "package_id": package_id, "phone": "12345"},
        )

    assert response.status_code == 422


def test_initiate_payment_with_an_invalid_router_token_is_rejected() -> None:
    response = client.post(
        "/api/v1/public/captive-portal/payments/initiate",
        json={
            "router": "garbage",
            "package_id": "00000000-0000-0000-0000-000000000000",
            "phone": "0712345678",
        },
    )
    assert response.status_code == 401


def test_status_for_an_unknown_token_reports_not_found() -> None:
    response = client.get(
        "/api/v1/public/captive-portal/payments/status", params={"token": "not-a-real-token"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "not_found",
        "login_username": None,
        "login_password": None,
    }


def test_full_payment_flow_reaches_completed_with_radius_credentials() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        router_id, package_id = _create_router_and_package(headers)
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]

        initiate_response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"router": router_token, "package_id": package_id, "phone": "0712345671"},
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
            # docstring) — drives the real activation/RADIUS-provisioning
            # path directly. Must run before SeededContext's teardown
            # (which cascades-deletes the tenant this transaction belongs
            # to), so it stays inside this `with` block.
            asyncio.run(_mark_completed_directly(transaction_id))

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
