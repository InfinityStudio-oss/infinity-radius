"""Super Admin tenant review workflow — see app/services/admin_tenants.py.
Resend is deliberately never mocked here either — unconfigured in tests,
so every send_* call exercises its real fail-soft path and never blocks
the actual status transition being tested.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


def test_approve_requires_super_admin() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(status="PENDING_VERIFICATION")
        ctx.new_tenant_verification(tenant_id=tenant_id)
        non_admin_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/approve",
            headers=auth_header(user_id=non_admin_id),
        )
    assert response.status_code == 403


def test_approve_unauthenticated_is_denied() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(status="PENDING_VERIFICATION")
        ctx.new_tenant_verification(tenant_id=tenant_id)

        response = client.post(f"/api/v1/admin/tenants/{tenant_id}/approve")
    assert response.status_code == 401


def test_approve_activates_tenant_without_touching_finance_flags() -> None:
    """Business approval and financial access are independent decisions —
    approving a tenant must never silently turn on Collections/Payouts."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(status="PENDING_VERIFICATION")
        ctx.new_tenant_verification(tenant_id=tenant_id)
        ctx.new_tenant_feature_flags(tenant_id=tenant_id)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/approve", headers=auth_header(user_id=admin_id)
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ACTIVE"

        # The tenant's owner can now reach a tenant-scoped endpoint —
        # app.core.context.get_tenant_context's ACTIVE-only gate passes.
        me = client.get("/api/v1/auth/me", headers=auth_header(user_id=owner_id))
        assert me.json()["data"]["tenant_status"] == "ACTIVE"

        detail = client.get(
            f"/api/v1/admin/tenants/{tenant_id}", headers=auth_header(user_id=admin_id)
        )
        detail_data = detail.json()["data"]
        assert detail_data["verification"]["status"] == "APPROVED"
        assert detail_data["collection_enabled"] is False
        assert detail_data["payout_enabled"] is False


def test_super_admin_can_independently_toggle_collection_and_payout() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(status="ACTIVE")
        ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED")
        ctx.new_tenant_feature_flags(tenant_id=tenant_id)
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        headers = auth_header(user_id=admin_id)

        enable_collection = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/collection", headers=headers, json={"enabled": True}
        )
        assert enable_collection.status_code == 200
        assert enable_collection.json()["data"]["collection_enabled"] is True
        assert enable_collection.json()["data"]["payout_enabled"] is False

        enable_payout = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/payout", headers=headers, json={"enabled": True}
        )
        assert enable_payout.status_code == 200
        assert enable_payout.json()["data"]["payout_enabled"] is True
        # Enabling payout doesn't touch collection, which stays as set above.
        assert enable_payout.json()["data"]["collection_enabled"] is True

        disable_collection = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/collection",
            headers=headers,
            json={"enabled": False},
        )
        assert disable_collection.json()["data"]["collection_enabled"] is False
        assert disable_collection.json()["data"]["payout_enabled"] is True

        audit_actions = {
            row["action"]
            for row in client.get(
                f"/api/v1/admin/tenants/{tenant_id}", headers=headers
            ).json()["data"]["recent_audit_logs"]
        }
        assert "TENANT_COLLECTION_ENABLED" in audit_actions
        assert "TENANT_COLLECTION_DISABLED" in audit_actions
        assert "TENANT_PAYOUT_ENABLED" in audit_actions


def test_non_super_admin_cannot_toggle_financial_flags() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(status="ACTIVE")
        ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED")
        ctx.new_tenant_feature_flags(tenant_id=tenant_id)
        non_admin_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/collection",
            headers=auth_header(user_id=non_admin_id),
            json={"enabled": True},
        )
    assert response.status_code == 403


def test_reject_requires_reason_field() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(status="PENDING_VERIFICATION")
        ctx.new_tenant_verification(tenant_id=tenant_id)
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/reject",
            headers=auth_header(user_id=admin_id),
            json={},
        )
    assert response.status_code == 422


def test_reject_sets_status_and_reason() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(status="PENDING_VERIFICATION")
        ctx.new_tenant_verification(tenant_id=tenant_id)
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/reject",
            headers=auth_header(user_id=admin_id),
            json={"reason": "Business license could not be verified"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "REJECTED"

        detail = client.get(
            f"/api/v1/admin/tenants/{tenant_id}", headers=auth_header(user_id=admin_id)
        )
        verification = detail.json()["data"]["verification"]
        assert verification["status"] == "REJECTED"
        assert verification["rejection_reason"] == "Business license could not be verified"


def test_request_more_information_sets_status_and_message() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(status="PENDING_VERIFICATION")
        ctx.new_tenant_verification(tenant_id=tenant_id)
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        response = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/request-more-information",
            headers=auth_header(user_id=admin_id),
            json={"message": "Please provide a copy of your TIN certificate"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "MORE_INFORMATION_REQUIRED"

        # The tenant owner still cannot reach a tenant-scoped endpoint —
        # MORE_INFORMATION_REQUIRED is not ACTIVE.
        routers = client.get("/api/v1/routers", headers=auth_header(user_id=owner_id))
        assert routers.status_code == 403


def test_suspend_and_reactivate_tenant() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant(status="ACTIVE")
        ctx.new_tenant_verification(tenant_id=tenant_id, status="APPROVED")
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        suspend = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/suspend",
            headers=auth_header(user_id=admin_id),
            json={"reason": "Payment dispute under review"},
        )
        assert suspend.status_code == 200
        assert suspend.json()["data"]["status"] == "SUSPENDED"

        blocked = client.get("/api/v1/routers", headers=auth_header(user_id=owner_id))
        assert blocked.status_code == 403

        reactivate = client.post(
            f"/api/v1/admin/tenants/{tenant_id}/reactivate", headers=auth_header(user_id=admin_id)
        )
        assert reactivate.status_code == 200
        assert reactivate.json()["data"]["status"] == "ACTIVE"

        restored = client.get("/api/v1/routers", headers=auth_header(user_id=owner_id))
        assert restored.status_code == 200


def test_list_queue_filters_by_status() -> None:
    with SeededContext() as ctx_a, SeededContext() as ctx_b:
        admin_id = ctx_a.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        pending_tenant = ctx_a.new_tenant(name="Pending Co", status="PENDING_VERIFICATION")
        ctx_a.new_tenant_verification(tenant_id=pending_tenant)
        ctx_a.new_user(role_code="TENANT_OWNER", tenant_id=pending_tenant)

        active_tenant = ctx_b.new_tenant(name="Active Co", status="ACTIVE")
        ctx_b.new_tenant_verification(tenant_id=active_tenant, status="APPROVED")
        ctx_b.new_user(role_code="TENANT_OWNER", tenant_id=active_tenant)

        pending_response = client.get(
            "/api/v1/admin/tenants?status=PENDING_VERIFICATION",
            headers=auth_header(user_id=admin_id),
        )
        pending_ids = {row["id"] for row in pending_response.json()["data"]}
        assert str(pending_tenant) in pending_ids
        assert str(active_tenant) not in pending_ids

        active_response = client.get(
            "/api/v1/admin/tenants?status=ACTIVE", headers=auth_header(user_id=admin_id)
        )
        active_ids = {row["id"] for row in active_response.json()["data"]}
        assert str(active_tenant) in active_ids
        assert str(pending_tenant) not in active_ids


def test_list_queue_never_hides_a_tenant_with_no_owner_profile() -> None:
    """Regression test: a tenant whose sole owner profile was later
    converted away (e.g. promoted to a platform SUPER_ADMIN account, or
    any other integrity gap) must still be visible to a Super Admin —
    never silently dropped by an inner join. See
    AdminTenantService.list_queue."""
    with SeededContext() as ctx_admin, SeededContext() as ctx_owned, SeededContext() as ctx_orphan:
        admin_id = ctx_admin.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        owned_tenant = ctx_owned.new_tenant(name="Has An Owner Co", status="PENDING_VERIFICATION")
        ctx_owned.new_tenant_verification(tenant_id=owned_tenant)
        ctx_owned.new_user(role_code="TENANT_OWNER", tenant_id=owned_tenant)

        # Deliberately ownerless: a verification row exists but no profile
        # anywhere claims tenant_id = orphan_tenant.
        orphan_tenant = ctx_orphan.new_tenant(name="Ownerless Co", status="PENDING_VERIFICATION")
        ctx_orphan.new_tenant_verification(tenant_id=orphan_tenant)

        response = client.get(
            "/api/v1/admin/tenants?status=all", headers=auth_header(user_id=admin_id)
        )
        assert response.status_code == 200
        rows_by_id = {row["id"]: row for row in response.json()["data"]}

        assert str(owned_tenant) in rows_by_id
        assert rows_by_id[str(owned_tenant)]["owner_missing"] is False
        assert rows_by_id[str(owned_tenant)]["owner_email"] is not None

        assert str(orphan_tenant) in rows_by_id, "ownerless tenant must not vanish from the queue"
        assert rows_by_id[str(orphan_tenant)]["owner_missing"] is True
        assert rows_by_id[str(orphan_tenant)]["owner_name"] is None
        assert rows_by_id[str(orphan_tenant)]["owner_email"] is None


def test_list_queue_filters_cover_every_status() -> None:
    with (
        SeededContext() as ctx_admin,
        SeededContext() as ctx_pending,
        SeededContext() as ctx_rejected,
        SeededContext() as ctx_suspended,
    ):
        admin_id = ctx_admin.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        pending = ctx_pending.new_tenant(name="Pending Co", status="PENDING_VERIFICATION")
        ctx_pending.new_tenant_verification(tenant_id=pending)

        rejected = ctx_rejected.new_tenant(name="Rejected Co", status="REJECTED")
        ctx_rejected.new_tenant_verification(tenant_id=rejected, status="REJECTED")

        suspended = ctx_suspended.new_tenant(name="Suspended Co", status="SUSPENDED")
        ctx_suspended.new_tenant_verification(tenant_id=suspended, status="APPROVED")

        for status_filter, expected_id in (
            ("PENDING_VERIFICATION", pending),
            ("REJECTED", rejected),
            ("SUSPENDED", suspended),
        ):
            response = client.get(
                f"/api/v1/admin/tenants?status={status_filter}",
                headers=auth_header(user_id=admin_id),
            )
            assert response.status_code == 200
            ids = {row["id"] for row in response.json()["data"]}
            assert str(expected_id) in ids

        all_response = client.get(
            "/api/v1/admin/tenants?status=all", headers=auth_header(user_id=admin_id)
        )
        all_ids = {row["id"] for row in all_response.json()["data"]}
        assert {str(pending), str(rejected), str(suspended)}.issubset(all_ids)


def test_tenant_detail_of_ownerless_tenant_does_not_crash() -> None:
    with SeededContext() as ctx_admin, SeededContext() as ctx_orphan:
        admin_id = ctx_admin.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        orphan_tenant = ctx_orphan.new_tenant(
            name="Ownerless Detail Co", status="PENDING_VERIFICATION"
        )
        ctx_orphan.new_tenant_verification(tenant_id=orphan_tenant)

        response = client.get(
            f"/api/v1/admin/tenants/{orphan_tenant}", headers=auth_header(user_id=admin_id)
        )
        assert response.status_code == 200
        detail = response.json()["data"]
        assert detail["owner_missing"] is True
        assert detail["owner_name"] is None
        assert detail["owner_email"] is None
        assert detail["owner_phone"] is None
