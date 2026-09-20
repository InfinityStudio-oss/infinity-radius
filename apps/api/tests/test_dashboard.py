"""Tenant dashboard landing page — real backend aggregation, no mocks.
Every card/chart endpoint is proven honest on a brand-new (empty) tenant
first (zeros/empty arrays, never a placeholder), then against real seeded
rows to prove the aggregation itself is correct, and finally that two
tenants never see each other's numbers.
"""

import asyncio
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient

from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.wallet import WalletService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def _create_package(headers: dict[str, str], *, price: str = "1000") -> str:
    response = client.post(
        "/api/v1/packages",
        headers=headers,
        json={
            "name": "Dashboard Package",
            "price_tzs": price,
            "duration_minutes": 60,
            "activation_type": "immediate",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


def _create_router(headers: dict[str, str], *, name: str = "Dashboard Router") -> str:
    response = client.post("/api/v1/routers", headers=headers, json={"name": name})
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


async def _process_collection(tenant_id: UUID, amount: str) -> None:
    async with AsyncSessionLocal() as db:
        await WalletService(db).process_collection(
            tenant_id=tenant_id,
            gross_amount=Decimal(amount),
            reference_type="test",
            reference_id=None,
            description="dashboard test collection",
        )
        await db.commit()


def test_summary_is_all_zero_for_a_brand_new_tenant() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get("/api/v1/dashboard/summary", headers=auth_header(user_id=user_id))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["online_users"] == 0
    assert Decimal(data["today_collections_tzs"]) == 0
    assert data["active_vouchers"] == 0
    assert data["routers_online"] == 0
    assert data["routers_total"] == 0
    assert data["failed_transactions"] == 0
    assert Decimal(data["available_wallet_balance_tzs"]) == 0


def test_summary_reflects_real_rows() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)

        # Two routers, only one online — real column values, never fabricated.
        router_id = _create_router(headers, name="Online Router")
        _create_router(headers, name="Unknown Router")
        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute("UPDATE routers SET status = 'online' WHERE id = %s", (router_id,))

        # One unused voucher.
        package_id = _create_package(headers)
        batch_response = client.post(
            "/api/v1/vouchers/batches",
            headers=headers,
            json={"package_id": package_id, "quantity": 1},
        )
        assert batch_response.status_code == 201

        # A real gross-to-net collection, seeding both today_collections and
        # the wallet's available balance (adjusted directly, mirroring the
        # settle_pending step — see app/services/wallet.py).
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="10.00")
        asyncio.run(_process_collection(tenant_id, "1000.00"))
        wallet_response = client.post(
            f"/api/v1/tenants/{tenant_id}/wallet/adjustments",
            headers=auth_header(user_id=admin_id),
            json={
                "wallet_bucket": "available",
                "direction": "credit",
                "amount": "500.00",
                "reason": "dashboard test — seed available balance",
            },
        )
        assert wallet_response.status_code == 201

        # A real failed transaction. Uppercase CollectionStatus, which is
        # what both writers actually persist — the lowercase spelling this
        # previously used was a value no writer has ever produced, so the
        # dashboard's own lowercase comparison matched it and the pair
        # agreed with each other while both disagreed with production.
        with ctx._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO transactions "
                "(tenant_id, reference, amount, currency, status, transaction_type) "
                "VALUES (%s, %s, %s, 'TZS', 'FAILED', 'COLLECTION')",
                (str(tenant_id), "DASH-FAILED-1", "250.00"),
            )

        # A real online session.
        with ctx._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_sessions (tenant_id, status, started_at) "
                "VALUES (%s, 'active', now())",
                (str(tenant_id),),
            )

        response = client.get("/api/v1/dashboard/summary", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["online_users"] == 1
    assert Decimal(data["today_collections_tzs"]) == Decimal("1000.00")
    assert data["active_vouchers"] == 1
    assert data["routers_online"] == 1
    assert data["routers_total"] == 2
    assert data["failed_transactions"] == 1
    assert Decimal(data["available_wallet_balance_tzs"]) == Decimal("500.00")


def test_summary_is_tenant_isolated() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant()
        tenant_b = ctx_b.new_tenant()
        user_a = ctx_a.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_a)
        user_b = ctx_b.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_b)

        _create_router(auth_header(user_id=user_a), name="Tenant A Router")

        response_a = client.get(
            "/api/v1/dashboard/summary", headers=auth_header(user_id=user_a)
        )
        response_b = client.get(
            "/api/v1/dashboard/summary", headers=auth_header(user_id=user_b)
        )

    assert response_a.json()["data"]["routers_total"] == 1
    assert response_b.json()["data"]["routers_total"] == 0


def test_collections_trend_is_empty_when_nothing_collected() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get(
            "/api/v1/dashboard/collections-trend", headers=auth_header(user_id=user_id)
        )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_collections_trend_reports_a_real_data_point() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        ctx.new_commercial_terms(tenant_id=tenant_id, commission_rate_percent="0.00")
        asyncio.run(_process_collection(tenant_id, "750.00"))

        response = client.get(
            "/api/v1/dashboard/collections-trend", headers=auth_header(user_id=user_id)
        )

    points = response.json()["data"]
    assert len(points) > 0
    total = sum(Decimal(p["collections_tzs"]) for p in points)
    assert total == Decimal("750.00")


def test_session_trend_is_empty_when_no_sessions_exist() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get(
            "/api/v1/dashboard/session-trend", headers=auth_header(user_id=user_id)
        )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_package_performance_is_empty_with_no_subscription_activity() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        _create_package(headers)  # a package exists, but nobody has subscribed

        response = client.get("/api/v1/dashboard/package-performance", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_package_performance_reports_real_subscription_and_revenue_aggregates() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        package_id = _create_package(headers, price="1500")

        customer_response = client.post(
            "/api/v1/customers",
            headers=headers,
            json={"first_name": "Pkg", "last_name": "Perf", "phone": "0712345699"},
        )
        assert customer_response.status_code == 201
        customer_id = customer_response.json()["data"]["id"]

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO subscriptions (tenant_id, customer_id, package_id, status) "
                "VALUES (%s, %s, %s, 'ACTIVE') RETURNING id",
                (str(tenant_id), customer_id, package_id),
            )
            row = cur.fetchone()
            assert row is not None
            (subscription_id,) = row
            cur.execute(
                "INSERT INTO subscriptions (tenant_id, customer_id, package_id, status) "
                "VALUES (%s, %s, %s, 'EXPIRED')",
                (str(tenant_id), customer_id, package_id),
            )
            # Uppercase COMPLETED — see the note in
            # test_summary_reflects_real_rows above.
            cur.execute(
                "INSERT INTO transactions "
                "(tenant_id, subscription_id, reference, amount, currency, status, "
                "transaction_type) "
                "VALUES (%s, %s, %s, %s, 'TZS', 'COMPLETED', 'COLLECTION')",
                (str(tenant_id), str(subscription_id), "DASH-PKG-PERF-1", "1500.00"),
            )

        response = client.get("/api/v1/dashboard/package-performance", headers=headers)

    assert response.status_code == 200
    rows = response.json()["data"]
    assert len(rows) == 1
    assert rows[0]["package_id"] == package_id
    assert rows[0]["total_subscriptions"] == 2
    assert rows[0]["active_subscriptions"] == 1
    assert Decimal(rows[0]["revenue_tzs"]) == Decimal("1500.00")


def test_router_health_route_is_reachable_and_not_shadowed_by_router_id() -> None:
    """Regression test for the same class of bug fixed in payouts.py:
    /health must be registered before /{router_id}, or FastAPI tries (and
    fails) to parse "health" as a UUID."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)
        headers = auth_header(user_id=user_id)
        _create_router(headers, name="Health Check Router")

        response = client.get("/api/v1/routers/health", headers=headers)

    assert response.status_code == 200
    rows = response.json()["data"]
    assert len(rows) == 1
    assert rows[0]["name"] == "Health Check Router"
    assert rows[0]["status"] == "unknown"
    # No telemetry pipeline exists — these must never be a guessed number.
    assert rows[0]["active_users"] is None
    assert rows[0]["latency_ms"] is None
    assert rows[0]["cpu_load_pct"] is None
    assert rows[0]["uptime_seconds"] is None


def test_router_health_is_empty_with_no_routers_configured() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.get("/api/v1/routers/health", headers=auth_header(user_id=user_id))

    assert response.status_code == 200
    assert response.json()["data"] == []
