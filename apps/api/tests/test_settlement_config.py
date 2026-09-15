"""Tenant settlement mode — which disbursement architecture applies to a
tenant. Never assumed: with no explicit configuration a tenant is
DIRECT_MERCHANT_SETTLEMENT (see app.core.enums.SettlementMode), managed
only by a super admin via `/api/v1/tenants/{tenant_id}/settlement-config`.
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_tenant_admin_cannot_set_settlement_config() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            f"/api/v1/tenants/{tenant_id}/settlement-config",
            headers=auth_header(user_id=user_id),
            json={"mode": "platform_managed_wallet"},
        )

    assert response.status_code == 403


def test_get_settlement_config_for_unconfigured_tenant_returns_null() -> None:
    """No row at all — the tenant is implicitly DIRECT_MERCHANT_SETTLEMENT
    (the safe default), not the other way around. See
    SettlementConfigService.get_mode."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get(
            f"/api/v1/tenants/{tenant_id}/settlement-config",
            headers=auth_header(user_id=admin_id),
        )

    assert response.status_code == 200
    assert response.json()["data"] is None


def test_super_admin_switches_tenant_to_platform_managed_wallet() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        headers = auth_header(user_id=admin_id)

        create_response = client.post(
            f"/api/v1/tenants/{tenant_id}/settlement-config",
            headers=headers,
            json={"mode": "platform_managed_wallet", "notes": "Approved by finance"},
        )
        assert create_response.status_code == 201
        created = create_response.json()["data"]
        assert created["mode"] == "platform_managed_wallet"
        assert created["is_active"] is True

        get_response = client.get(
            f"/api/v1/tenants/{tenant_id}/settlement-config", headers=headers
        )

    assert get_response.status_code == 200
    assert get_response.json()["data"]["mode"] == "platform_managed_wallet"


def test_setting_the_same_mode_twice_is_rejected() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        headers = auth_header(user_id=admin_id)

        first = client.post(
            f"/api/v1/tenants/{tenant_id}/settlement-config",
            headers=headers,
            json={"mode": "platform_managed_wallet"},
        )
        assert first.status_code == 201

        second = client.post(
            f"/api/v1/tenants/{tenant_id}/settlement-config",
            headers=headers,
            json={"mode": "platform_managed_wallet"},
        )

    assert second.status_code == 422


def test_switching_mode_deactivates_the_previous_row_and_keeps_history() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        headers = auth_header(user_id=admin_id)

        client.post(
            f"/api/v1/tenants/{tenant_id}/settlement-config",
            headers=headers,
            json={"mode": "platform_managed_wallet"},
        )
        second = client.post(
            f"/api/v1/tenants/{tenant_id}/settlement-config",
            headers=headers,
            json={"mode": "direct_merchant_settlement"},
        )
        assert second.status_code == 201

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT mode, is_active FROM tenant_settlement_config "
                "WHERE tenant_id = %s ORDER BY created_at",
                (str(tenant_id),),
            )
            rows = cur.fetchall()

    assert len(rows) == 2
    assert [bool(is_active) for _mode, is_active in rows] == [False, True]


def test_settlement_config_for_unknown_tenant_is_not_found() -> None:
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(
            f"/api/v1/tenants/{uuid4()}/settlement-config",
            headers=auth_header(user_id=admin_id),
            json={"mode": "platform_managed_wallet"},
        )

    assert response.status_code == 404
