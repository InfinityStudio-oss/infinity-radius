"""Tenant commercial terms — the platform commission rate. Never hard-coded:
every tenant needs its own configured, versioned rate, managed only by a
super admin (`/api/v1/tenants/{tenant_id}/commercial-terms`).
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_tenant_admin_cannot_set_commercial_terms() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        user_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            f"/api/v1/tenants/{tenant_id}/commercial-terms",
            headers=auth_header(user_id=user_id),
            json={"commission_rate_percent": "10.00"},
        )

    assert response.status_code == 403


def test_get_commercial_terms_for_unconfigured_tenant_returns_null() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.get(
            f"/api/v1/tenants/{tenant_id}/commercial-terms",
            headers=auth_header(user_id=admin_id),
        )

    assert response.status_code == 200
    assert response.json()["data"] is None


def test_super_admin_sets_and_reads_back_commercial_terms() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        headers = auth_header(user_id=admin_id)

        create_response = client.post(
            f"/api/v1/tenants/{tenant_id}/commercial-terms",
            headers=headers,
            json={"commission_rate_percent": "12.50", "notes": "Standard ISP tier"},
        )
        assert create_response.status_code == 201
        created = create_response.json()["data"]
        assert created["commission_rate_percent"] == "12.50"
        assert created["is_active"] is True
        assert created["notes"] == "Standard ISP tier"

        get_response = client.get(
            f"/api/v1/tenants/{tenant_id}/commercial-terms", headers=headers
        )

    assert get_response.status_code == 200
    assert get_response.json()["data"]["commission_rate_percent"] == "12.50"


def test_setting_a_new_rate_supersedes_the_previous_one() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        headers = auth_header(user_id=admin_id)

        client.post(
            f"/api/v1/tenants/{tenant_id}/commercial-terms",
            headers=headers,
            json={"commission_rate_percent": "10.00"},
        )
        second = client.post(
            f"/api/v1/tenants/{tenant_id}/commercial-terms",
            headers=headers,
            json={"commission_rate_percent": "15.00"},
        )
        assert second.status_code == 201

        get_response = client.get(
            f"/api/v1/tenants/{tenant_id}/commercial-terms", headers=headers
        )

        assert ctx._conn is not None
        with ctx._conn.cursor() as cur:
            cur.execute(
                "SELECT commission_rate_percent, is_active FROM tenant_commercial_terms "
                "WHERE tenant_id = %s ORDER BY created_at",
                (str(tenant_id),),
            )
            rows = cur.fetchall()

    # Only ever one active row per tenant — history is preserved, not overwritten.
    assert get_response.json()["data"]["commission_rate_percent"] == "15.00"
    assert len(rows) == 2
    assert [bool(is_active) for _rate, is_active in rows] == [False, True]


def test_commission_rate_must_be_within_0_to_100() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(
            f"/api/v1/tenants/{tenant_id}/commercial-terms",
            headers=auth_header(user_id=admin_id),
            json={"commission_rate_percent": "150.00"},
        )

    assert response.status_code == 422


def test_commercial_terms_for_unknown_tenant_is_not_found() -> None:
    with SeededContext() as ctx:
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(
            f"/api/v1/tenants/{uuid4()}/commercial-terms",
            headers=auth_header(user_id=admin_id),
            json={"commission_rate_percent": "10.00"},
        )

    assert response.status_code == 404
