"""Proves cross-tenant isolation end to end through the real HTTP API —
not just at the repository layer. Tenant A's data must be completely
invisible (never a 200 with someone else's row, never a leaked total) to
Tenant B, to an unauthenticated caller, and reachable only in the right
shape to a SUPER_ADMIN.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_unauthenticated_caller_is_denied_every_tenant_resource() -> None:
    for path in ["/api/v1/customers", "/api/v1/routers", "/api/v1/packages",
                 "/api/v1/subscriptions", "/api/v1/sessions", "/api/v1/wallet",
                 "/api/v1/vouchers/batches"]:
        assert client.get(path).status_code == 401


def test_tenant_a_cannot_read_tenant_b_customers_routers_packages() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant()
        owner_a = ctx_a.new_user(role_code="TENANT_OWNER", tenant_id=tenant_a)
        headers_a = auth_header(user_id=owner_a)

        tenant_b = ctx_b.new_tenant()
        owner_b = ctx_b.new_user(role_code="TENANT_OWNER", tenant_id=tenant_b)
        headers_b = auth_header(user_id=owner_b)

        customer = client.post(
            "/api/v1/customers",
            headers=headers_a,
            json={"first_name": "Neema", "last_name": "Kileo", "phone": "0712000001"},
        ).json()["data"]

        router = client.post(
            "/api/v1/routers", headers=headers_a, json={"name": "Isolation Test Router"}
        ).json()["data"]

        package = client.post(
            "/api/v1/packages",
            headers=headers_a,
            json={"name": "Isolation Test Package", "price_tzs": "1000.00", "device_limit": 1},
        ).json()["data"]

        # Tenant B's own lists are empty — tenant A's rows never leak in.
        assert client.get("/api/v1/customers", headers=headers_b).json()["data"] == []
        assert client.get("/api/v1/routers", headers=headers_b).json()["data"] == []
        assert client.get("/api/v1/packages", headers=headers_b).json()["data"] == []

        # Tenant B cannot fetch tenant A's specific rows by id either.
        assert (
            client.get(f"/api/v1/routers/{router['id']}", headers=headers_b).status_code == 404
        )
        assert (
            client.get(f"/api/v1/packages/{package['id']}", headers=headers_b).status_code == 404
        )

        # Tenant B cannot modify tenant A's router.
        assert (
            client.post(
                f"/api/v1/routers/{router['id']}/test-connection", headers=headers_b
            ).status_code
            == 404
        )

        # Tenant A can still see its own rows — isolation isn't just "everyone denied".
        assert client.get("/api/v1/customers", headers=headers_a).json()["data"][0]["id"] == (
            customer["id"]
        )


def test_tenant_a_cannot_read_tenant_b_subscriptions_or_vouchers() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant()
        owner_a = ctx_a.new_user(role_code="TENANT_OWNER", tenant_id=tenant_a)
        headers_a = auth_header(user_id=owner_a)

        tenant_b = ctx_b.new_tenant()
        owner_b = ctx_b.new_user(role_code="TENANT_OWNER", tenant_id=tenant_b)
        headers_b = auth_header(user_id=owner_b)

        package = client.post(
            "/api/v1/packages",
            headers=headers_a,
            json={"name": "Sub Package", "price_tzs": "500.00", "device_limit": 1},
        ).json()["data"]
        customer = client.post(
            "/api/v1/customers",
            headers=headers_a,
            json={"first_name": "Baraka", "last_name": "Nyerere", "phone": "0712000002"},
        ).json()["data"]
        subscription = client.post(
            "/api/v1/subscriptions",
            headers=headers_a,
            json={"customer_id": customer["id"], "package_id": package["id"]},
        ).json()["data"]

        batch = client.post(
            "/api/v1/vouchers/batches",
            headers=headers_a,
            json={"package_id": package["id"], "quantity": 1},
        ).json()["data"]

        assert client.get("/api/v1/subscriptions", headers=headers_b).json()["data"] == []
        assert (
            client.get(
                f"/api/v1/subscriptions/{subscription['id']}", headers=headers_b
            ).status_code
            == 404
        )

        assert client.get("/api/v1/vouchers/batches", headers=headers_b).json()["data"] == []
        assert (
            client.get(f"/api/v1/vouchers/batches/{batch['id']}", headers=headers_b).status_code
            == 404
        )


def test_tenant_a_cannot_read_tenant_b_wallet_or_sessions() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        tenant_a = ctx_a.new_tenant()
        owner_a = ctx_a.new_user(role_code="TENANT_OWNER", tenant_id=tenant_a)

        tenant_b = ctx_b.new_tenant()
        owner_b = ctx_b.new_user(role_code="TENANT_OWNER", tenant_id=tenant_b)
        headers_b = auth_header(user_id=owner_b)

        # Give tenant A a wallet with a nonzero balance via the one
        # sanctioned path (an admin adjustment) so there's something real
        # for tenant B to fail to see.
        admin_id = ctx_a.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        client.post(
            f"/api/v1/tenants/{tenant_a}/wallet/adjustments",
            headers=auth_header(user_id=admin_id),
            json={
                "wallet_bucket": "available",
                "direction": "credit",
                "amount": "5000.00",
                "reason": "isolation test seed",
            },
        )

        # Tenant B's own wallet reflects only tenant B — never tenant A's balance.
        wallet_b = client.get("/api/v1/wallet", headers=headers_b).json()["data"]
        assert wallet_b["available_balance_tzs"] == "0.00"

        assert client.get("/api/v1/sessions", headers=headers_b).json()["data"] == []
        assert client.get("/api/v1/wallet/ledger", headers=headers_b).json()["data"] == []

        _ = owner_a  # seeded for realism; not directly asserted on


def test_super_admin_can_access_platform_level_tenant_data() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get(
            f"/api/v1/tenants/{tenant_id}", headers=auth_header(user_id=admin_id)
        )
        assert response.status_code == 200
        assert response.json()["data"]["id"] == str(tenant_id)


def test_super_admin_is_rejected_by_tenant_scoped_routes() -> None:
    """A platform-wide super admin has no tenant_id — tenant-only routes
    (get_tenant_context) reject them just like an unaffiliated account,
    exactly as app.core.context's own docstring states."""
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        response = client.get("/api/v1/customers", headers=auth_header(user_id=admin_id))
    assert response.status_code == 403
