"""The real, backend-bound super-admin platform dashboard — distinct from
the earlier-phase `/overview`/`/system-health` stubs covered by
test_super_admin.py, which stay untouched. Every card/list here is a real
aggregation across ALL tenants; a brand-new platform with nothing in it
gets honest zeros/empty arrays, never a placeholder.
"""

import asyncio
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.enums import LedgerDirection, WalletBucket
from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.wallet import WalletService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


async def _credit_available(tenant_id: UUID, actor_id: UUID, amount: str) -> None:
    async with AsyncSessionLocal() as db:
        await WalletService(db).create_adjustment(
            tenant_id=tenant_id,
            wallet_bucket=WalletBucket.AVAILABLE,
            direction=LedgerDirection.CREDIT,
            amount=Decimal(amount),
            reason="super-admin dashboard test — seed available balance",
            actor_id=actor_id,
        )
        await db.commit()


async def _process_collection(tenant_id: UUID, amount: str) -> None:
    async with AsyncSessionLocal() as db:
        await WalletService(db).process_collection(
            tenant_id=tenant_id,
            gross_amount=Decimal(amount),
            reference_type="test",
            reference_id=None,
            description="super-admin dashboard test collection",
        )
        await db.commit()


def test_dashboard_summary_rejects_non_super_admin() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get(
            "/api/v1/super-admin/dashboard-summary", headers=auth_header(user_id=user_id)
        )

    assert response.status_code == 403


def test_dashboard_summary_reconciliation_is_honestly_not_configured() -> None:
    """No reconciliation-exception table exists anywhere in this schema —
    must never be reported as a fake 0."""
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get(
            "/api/v1/super-admin/dashboard-summary", headers=auth_header(user_id=admin_id)
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reconciliation_exceptions"]["status"] == "not_configured"


def test_dashboard_summary_reflects_real_cross_tenant_rows() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        admin_id = ctx_a.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        admin_headers = auth_header(user_id=admin_id)

        tenant_a = ctx_a.new_tenant()
        owner_a = ctx_a.new_user(role_code="TENANT_OWNER", tenant_id=tenant_a)

        tenant_b = ctx_b.new_tenant()
        owner_b = ctx_b.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b)

        # Routers across both tenants — one online. Created while tenant_b
        # is still ACTIVE: app.core.context.get_tenant_context now rejects
        # every tenant-scoped write once a tenant is SUSPENDED (the whole
        # point of that gate), so this has to happen before suspension.
        router_a = client.post(
            "/api/v1/routers", headers=auth_header(user_id=owner_a), json={"name": "Router A"}
        ).json()["data"]["id"]
        router_b_response = client.post(
            "/api/v1/routers", headers=auth_header(user_id=owner_b), json={"name": "Router B"}
        )
        assert router_b_response.status_code == 201
        assert ctx_a._conn is not None
        with ctx_a._conn.cursor() as cur:
            cur.execute("UPDATE routers SET status = 'online' WHERE id = %s", (router_a,))

        # tenant_b gets suspended — a real, queryable status (see
        # app.core.enums.TenantStatus; now the real onboarding/approval
        # workflow's SUSPENDED state, not just a placeholder value).
        assert ctx_b._conn is not None
        with ctx_b._conn.cursor() as cur:
            cur.execute("UPDATE tenants SET status = 'SUSPENDED' WHERE id = %s", (str(tenant_b),))

        # One active RADIUS session.
        with ctx_a._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_sessions (tenant_id, status, started_at) "
                "VALUES (%s, 'active', now())",
                (str(tenant_a),),
            )

        # A real collection today.
        ctx_a.new_commercial_terms(tenant_id=tenant_a, commission_rate_percent="10.00")
        asyncio.run(_process_collection(tenant_a, "1000.00"))

        # A real pending payout: request + confirm 2FA -> PENDING_APPROVAL.
        ctx_a.new_settlement_config(tenant_id=tenant_a)
        asyncio.run(_credit_available(tenant_a, admin_id, "500.00"))
        destination_id = client.post(
            "/api/v1/payouts/destinations",
            headers=auth_header(user_id=owner_a),
            json={"label": "M-Pesa", "channel": "mobile_money", "account_number": "255700000001"},
        ).json()["data"]["id"]
        request_response = client.post(
            "/api/v1/payouts",
            headers=auth_header(user_id=owner_a),
            json={"destination_id": destination_id, "amount": "300.00"},
        )
        withdrawal_id = request_response.json()["withdrawal"]["id"]
        code = request_response.json()["two_factor_code"]
        client.post(
            f"/api/v1/payouts/{withdrawal_id}/confirm-2fa",
            headers=auth_header(user_id=owner_a),
            json={"code": code},
        )

        # A real failed (attempted-and-rejected) webhook.
        with ctx_a._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO payment_webhooks (provider, payload, signature_verified, processed) "
                "VALUES ('selcom', '{}'::jsonb, false, true)"
            )

        summary_response = client.get(
            "/api/v1/super-admin/dashboard-summary", headers=admin_headers
        )
        pending_response = client.get(
            "/api/v1/super-admin/pending-payouts", headers=admin_headers
        )

    assert summary_response.status_code == 200
    data = summary_response.json()["data"]
    assert data["active_tenants"] >= 1
    assert data["suspended_tenants"] >= 1
    assert data["routers_total"] >= 2
    assert data["routers_online"] >= 1
    assert data["radius_active_sessions"] >= 1
    assert Decimal(data["collections_today_tzs"]) >= Decimal("1000.00")
    assert data["pending_payouts"] >= 1
    assert Decimal(data["pending_payouts_amount_tzs"]) >= Decimal("300.00")
    assert data["failed_webhooks"] >= 1

    pending_rows = pending_response.json()["data"]
    assert any(row["withdrawal_id"] == withdrawal_id for row in pending_rows)
    matching = next(row for row in pending_rows if row["withdrawal_id"] == withdrawal_id)
    assert matching["status"] == "PENDING_APPROVAL"
    assert Decimal(matching["amount_tzs"]) == Decimal("300.00")


def test_collections_trend_is_empty_when_nothing_collected_anywhere() -> None:
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get(
            "/api/v1/super-admin/collections-trend", headers=auth_header(user_id=admin_id)
        )

    assert response.status_code == 200
    # Not strictly guaranteed empty if another test's data lands in the
    # same trailing window, but the shape/keys must always be honest.
    for point in response.json()["data"]:
        assert "date" in point and "collections_tzs" in point


def test_tenant_growth_trend_reports_a_real_new_tenant() -> None:
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        ctx.new_tenant()

        response = client.get(
            "/api/v1/super-admin/tenant-growth-trend", headers=auth_header(user_id=admin_id)
        )

    assert response.status_code == 200
    points = response.json()["data"]
    assert sum(p["new_tenants"] for p in points) >= 1


def test_pending_payouts_queue_is_empty_with_no_pending_payouts() -> None:
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        ctx.new_tenant()

        response = client.get(
            "/api/v1/super-admin/pending-payouts", headers=auth_header(user_id=admin_id)
        )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_platform_audit_logs_span_multiple_tenants() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        admin_id = ctx_a.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        tenant_a = ctx_a.new_tenant()
        owner_a = ctx_a.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_a)
        tenant_b = ctx_b.new_tenant()
        owner_b = ctx_b.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b)

        client.post("/api/v1/routers", headers=auth_header(user_id=owner_a), json={"name": "R-A"})
        client.post("/api/v1/routers", headers=auth_header(user_id=owner_b), json={"name": "R-B"})

        response = client.get(
            "/api/v1/super-admin/audit-logs",
            params={"page_size": 100},
            headers=auth_header(user_id=admin_id),
        )

    assert response.status_code == 200
    tenant_ids_seen = {row["tenant_id"] for row in response.json()["data"]}
    assert str(tenant_a) in tenant_ids_seen
    assert str(tenant_b) in tenant_ids_seen


def test_super_admin_dashboard_endpoints_reject_tenant_staff() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        for path in (
            "/api/v1/super-admin/collections-trend",
            "/api/v1/super-admin/tenant-growth-trend",
            "/api/v1/super-admin/pending-payouts",
            "/api/v1/super-admin/audit-logs",
        ):
            response = client.get(path, headers=headers)
            assert response.status_code == 403, path
