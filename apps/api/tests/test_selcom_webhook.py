"""POST /api/v1/webhooks/selcom/collection.

Selcom's real callback field names and signature scheme are unknown (see
app/integrations/selcom/signatures.py) — so `verify_callback` always
raises today, and every test that exercises the *domain* pipeline
downstream of verification (idempotency, reference/amount/state
validation, activation, wallet credit, RADIUS provisioning) does so by
monkeypatching `CollectionService.verify_callback` and its `_extract_*`
helpers for the duration of that one test only. This is a TEST-ONLY
simulation of a future verified state — nothing here is reachable from
runtime or UI code, and production's `verify_callback` is exercised
completely unpatched by the tests that don't monkeypatch it (proving it
still genuinely refuses to verify anything).
"""

from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.transaction_token import resolve_transaction_token
from app.integrations.selcom.collection import CollectionService
from app.main import app
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


def _create_router_and_package(headers: dict[str, str]) -> tuple[str, str]:
    router_id = client.post(
        "/api/v1/routers", headers=headers, json={"name": "Webhook Test Router"}
    ).json()["data"]["id"]
    package_id = client.post(
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
    ).json()["data"]["id"]
    return router_id, package_id


def _get_reference(ctx: SeededContext, transaction_id: object) -> str:
    assert ctx._conn is not None
    with ctx._conn.cursor() as cur:
        cur.execute("SELECT reference FROM transactions WHERE id = %s", (str(transaction_id),))
        row = cur.fetchone()
    assert row is not None
    return str(row[0])


def _fake_extractors(monkeypatch: pytest.MonkeyPatch, *, verified: bool = True) -> None:
    """Test-only stand-in for the (currently unimplemented) real callback
    parsing — see this file's module docstring. Reads a made-up test
    payload shape {"reference", "amount", "status"}; this is NOT a claim
    about Selcom's actual field names."""
    monkeypatch.setattr(CollectionService, "verify_callback", lambda self, **kw: verified)
    monkeypatch.setattr(
        CollectionService, "_extract_reference", lambda self, payload: payload["reference"]
    )
    monkeypatch.setattr(
        CollectionService,
        "_extract_amount",
        lambda self, payload: Decimal(payload["amount"]),
    )
    monkeypatch.setattr(
        CollectionService,
        "_extract_provider_status",
        lambda self, payload: payload["status"] == "success",
    )


def test_webhook_with_unimplemented_verification_saves_event_and_reports_unverified() -> None:
    response = client.post(
        "/api/v1/webhooks/selcom/collection", json={"anything": "at all"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "unverified"}


def test_webhook_with_unparsable_body_still_saves_an_event_and_reports_unverified() -> None:
    response = client.post(
        "/api/v1/webhooks/selcom/collection",
        content=b"not json at all",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "unverified"}


def test_verified_callback_completes_the_transaction_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            json={
                "router": router_token,
                "package_id": package_id,
                "phone": "0712345601",
                "mac_address": "AA:BB:CC:DD:EE:01",
            },
        )
        transaction_token = initiate_response.json()["transaction_token"]
        transaction_id = resolve_transaction_token(transaction_token)
        assert transaction_id is not None
        reference = _get_reference(ctx, transaction_id)

        try:
            _fake_extractors(monkeypatch)
            webhook_response = client.post(
                "/api/v1/webhooks/selcom/collection",
                json={"reference": reference, "amount": "1500.00", "status": "success"},
            )
            assert webhook_response.status_code == 200
            assert webhook_response.json() == {"status": "processed"}

            status_response = client.get(
                "/api/v1/public/captive-portal/payments/status",
                params={"token": transaction_token},
            )
            body = status_response.json()
            assert body["status"] == "completed"
            assert body["login_username"] == "255712345601"
            assert body["login_password"]

            # Wallet was really credited — gross 1500.00 split via the
            # tenant's 10% commercial terms into a 150.00 platform fee and
            # a 1350.00 tenant share landing in `pending` — real ledger
            # entries, not just a transaction-status flip.
            wallet_response = client.get("/api/v1/wallet", headers=headers)
            assert wallet_response.json()["data"]["pending_balance_tzs"] == "1350.00"
            ledger_response = client.get("/api/v1/wallet/ledger", headers=headers)
            ledger_items = ledger_response.json()["data"]
            assert len(ledger_items) == 3
            entries_by_type = {item["entry_type"]: item for item in ledger_items}
            assert entries_by_type["TENANT_SHARE"]["amount"] == "1350.00"
            assert entries_by_type["TENANT_SHARE"]["reference_id"] == str(transaction_id)

            # Real RADIUS credentials exist.
            conn = psycopg.connect(_radius_dsn())
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM radcheck WHERE username = %s "
                    "AND attribute = 'Cleartext-Password'",
                    ("255712345601",),
                )
                row = cur.fetchone()
            conn.close()
            assert row is not None
            assert row[0] == body["login_password"]
        finally:
            _cleanup_radius(username="255712345601", package_id=package_id)


def test_verified_callback_with_wrong_amount_is_rejected_and_leaves_transaction_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        router_id, package_id = _create_router_and_package(headers)
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]

        initiate_response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"router": router_token, "package_id": package_id, "phone": "0712345602"},
        )
        transaction_token = initiate_response.json()["transaction_token"]
        transaction_id = resolve_transaction_token(transaction_token)
        assert transaction_id is not None
        reference = _get_reference(ctx, transaction_id)

        _fake_extractors(monkeypatch)
        webhook_response = client.post(
            "/api/v1/webhooks/selcom/collection",
            json={"reference": reference, "amount": "1.00", "status": "success"},
        )
        assert webhook_response.status_code == 200
        assert webhook_response.json() == {"status": "error"}

        status_response = client.get(
            "/api/v1/public/captive-portal/payments/status", params={"token": transaction_token}
        )
        assert status_response.json()["status"] == "pending"


def test_verified_callback_reporting_failure_marks_transaction_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        router_id, package_id = _create_router_and_package(headers)
        router_token = client.get(
            f"/api/v1/routers/{router_id}/provisioning/public-token", headers=headers
        ).json()["data"]["router_token"]

        initiate_response = client.post(
            "/api/v1/public/captive-portal/payments/initiate",
            json={"router": router_token, "package_id": package_id, "phone": "0712345603"},
        )
        transaction_token = initiate_response.json()["transaction_token"]
        transaction_id = resolve_transaction_token(transaction_token)
        assert transaction_id is not None
        reference = _get_reference(ctx, transaction_id)

        _fake_extractors(monkeypatch)
        webhook_response = client.post(
            "/api/v1/webhooks/selcom/collection",
            json={"reference": reference, "amount": "1500.00", "status": "declined"},
        )
        assert webhook_response.status_code == 200
        assert webhook_response.json() == {"status": "failed"}

        status_response = client.get(
            "/api/v1/public/captive-portal/payments/status", params={"token": transaction_token}
        )
        assert status_response.json()["status"] == "failed"


def test_verified_callback_is_idempotent_on_retry(monkeypatch: pytest.MonkeyPatch) -> None:
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
            json={"router": router_token, "package_id": package_id, "phone": "0712345604"},
        )
        transaction_token = initiate_response.json()["transaction_token"]
        transaction_id = resolve_transaction_token(transaction_token)
        assert transaction_id is not None
        reference = _get_reference(ctx, transaction_id)

        try:
            _fake_extractors(monkeypatch)
            payload: dict[str, Any] = {
                "reference": reference,
                "amount": "1500.00",
                "status": "success",
            }
            first = client.post("/api/v1/webhooks/selcom/collection", json=payload)
            second = client.post("/api/v1/webhooks/selcom/collection", json=payload)

            assert first.json() == {"status": "processed"}
            assert second.json() == {"status": "duplicate"}

            # Only ONE collection's worth of ledger entries (3: COLLECTION +
            # PLATFORM_FEE + TENANT_SHARE), even though the webhook arrived twice.
            ledger_response = client.get("/api/v1/wallet/ledger", headers=headers)
            assert len(ledger_response.json()["data"]) == 3
        finally:
            _cleanup_radius(username="255712345604", package_id=package_id)


def test_verified_callback_for_an_unknown_reference_reports_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_extractors(monkeypatch)
    response = client.post(
        "/api/v1/webhooks/selcom/collection",
        json={"reference": "CP-DOESNOTEXIST", "amount": "1500.00", "status": "success"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "not_found"}
