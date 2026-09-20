"""Tenant-facing Collection read APIs used by the dashboard UI —
GET /api/v1/collections/summary and GET /api/v1/collections/{id}.

Every case here is about authorization and tenant isolation rather than
financial logic (that lives in test_collections_service.py): a tenant must
never see another tenant's Collections, and the summary must count only
its own.
"""

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.core.enums import CollectionStatus, TransactionType
from app.db.session import AsyncSessionLocal
from app.main import app
from app.repositories.finance import TransactionRepository
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


async def _seed_transaction(
    *,
    tenant_id: UUID,
    status: CollectionStatus,
    amount: str = "1000.00",
    transaction_type: str | None = TransactionType.COLLECTION.value,
) -> UUID:
    """Writes a transaction row directly through the repository — no
    provider call, no STK, no wallet movement. `transaction_type=None`
    simulates a row predating the discriminator migration."""
    async with AsyncSessionLocal() as db:
        transaction = await TransactionRepository(db).create(
            tenant_id=tenant_id,
            transaction_type=transaction_type,
            reference=f"col-{uuid4().hex}",
            amount=amount,
            currency="TZS",
            status=status.value,
            payer_phone="255712345678",
        )
        await db.commit()
        return transaction.id


async def _seed_captive_portal(*, tenant_id: UUID, status: str = "pending") -> UUID:
    """A captive-portal row shaped exactly like captive_portal.py writes
    one — the family the Collection views must never include."""
    async with AsyncSessionLocal() as db:
        transaction = await TransactionRepository(db).create(
            tenant_id=tenant_id,
            transaction_type=TransactionType.CAPTIVE_PORTAL.value,
            reference=f"CP-{uuid4().hex.upper()[:16]}",
            channel="captive_portal",
            amount="1500.00",
            currency="TZS",
            status=status,
        )
        await db.commit()
        return transaction.id


def test_summary_counts_only_the_callers_own_tenant() -> None:
    with SeededContext() as ctx:
        tenant_a = ctx.new_tenant()
        owner_a = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_a)
        tenant_b = ctx.new_tenant(name="Other Tenant")
        ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_b)

        asyncio.run(_seed_transaction(tenant_id=tenant_a, status=CollectionStatus.COMPLETED))
        asyncio.run(_seed_transaction(tenant_id=tenant_a, status=CollectionStatus.STK_SENT))
        asyncio.run(
            _seed_transaction(tenant_id=tenant_a, status=CollectionStatus.REQUIRES_REVIEW)
        )
        asyncio.run(_seed_transaction(tenant_id=tenant_a, status=CollectionStatus.CANCELLED))
        # Tenant B's rows must not leak into tenant A's totals.
        asyncio.run(_seed_transaction(tenant_id=tenant_b, status=CollectionStatus.COMPLETED))
        asyncio.run(_seed_transaction(tenant_id=tenant_b, status=CollectionStatus.COMPLETED))
        # Nor may tenant A's own captive-portal rows.
        asyncio.run(_seed_captive_portal(tenant_id=tenant_a))

        response = client.get("/api/v1/collections/summary", headers=auth_header(user_id=owner_a))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 4
    assert data["completed"] == 1
    assert data["in_progress"] == 1
    assert data["requires_attention"] == 1
    assert data["failed"] == 1
    assert data["by_status"] == {
        "COMPLETED": 1,
        "STK_SENT": 1,
        "REQUIRES_REVIEW": 1,
        "CANCELLED": 1,
    }


def test_summary_route_is_not_swallowed_by_the_transaction_id_route() -> None:
    """Regression guard: GET /collections/{transaction_id} is declared with
    a UUID path param, so if /summary were declared after it the literal
    "summary" would be parsed as a UUID and 422."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        response = client.get(
            "/api/v1/collections/summary", headers=auth_header(user_id=owner_id)
        )

    assert response.status_code == 200
    assert "total" in response.json()["data"]


def test_summary_is_zeroed_for_a_tenant_with_no_collections() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        response = client.get(
            "/api/v1/collections/summary", headers=auth_header(user_id=owner_id)
        )

    data = response.json()["data"]
    assert data["total"] == 0
    assert data["completed"] == 0
    assert data["by_status"] == {}


def test_summary_counts_an_unrecognised_status_in_total_and_by_status() -> None:
    """A status this dashboard build doesn't know about must still be
    counted, so the cards can never quietly under-report."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)

        async def _seed_unknown() -> None:
            async with AsyncSessionLocal() as db:
                await TransactionRepository(db).create(
                    tenant_id=tenant_id,
                    transaction_type=TransactionType.COLLECTION.value,
                    reference=f"col-{uuid4().hex}",
                    amount="1000.00",
                    currency="TZS",
                    status="SOME_FUTURE_STATUS",
                )
                await db.commit()

        asyncio.run(_seed_unknown())
        response = client.get(
            "/api/v1/collections/summary", headers=auth_header(user_id=owner_id)
        )

    data = response.json()["data"]
    assert data["total"] == 1
    assert data["by_status"] == {"SOME_FUTURE_STATUS": 1}
    # Not claimed as completed, in-progress, attention, or failed.
    assert data["completed"] == 0
    assert data["in_progress"] == 0
    assert data["requires_attention"] == 0
    assert data["failed"] == 0


def test_detail_route_refuses_another_tenants_collection() -> None:
    """Changing the id in the URL must never expose another tenant's
    payment — the lookup is tenant-scoped server-side."""
    with SeededContext() as ctx:
        tenant_a = ctx.new_tenant()
        owner_a = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_a)
        tenant_b = ctx.new_tenant(name="Other Tenant")
        ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_b)

        foreign_id = asyncio.run(
            _seed_transaction(tenant_id=tenant_b, status=CollectionStatus.COMPLETED)
        )

        response = client.get(
            f"/api/v1/collections/{foreign_id}", headers=auth_header(user_id=owner_a)
        )

    assert response.status_code == 404


def test_detail_route_returns_the_callers_own_collection() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        transaction_id = asyncio.run(
            _seed_transaction(tenant_id=tenant_id, status=CollectionStatus.COMPLETED)
        )

        response = client.get(
            f"/api/v1/collections/{transaction_id}", headers=auth_header(user_id=owner_id)
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(transaction_id)
    assert data["status"] == CollectionStatus.COMPLETED.value
    assert Decimal(data["amount"]) == Decimal("1000.00")
    # The raw payer phone is never returned — only the masked form.
    assert "payer_phone" not in data
    assert data["payer_phone_masked"] == "2557*****678"


def test_summary_requires_authentication() -> None:
    response = client.get("/api/v1/collections/summary")
    assert response.status_code == 401


# ---------------------------------------------------------------------
# GET /api/v1/collections — the type-scoped history list. These exist
# because `transactions` is shared with captive-portal payments, so
# "tenant-scoped" alone is not enough: the list must also be scoped to
# one payment family, server-side.


def test_list_returns_collection_rows_only() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)

        collection_id = asyncio.run(
            _seed_transaction(tenant_id=tenant_id, status=CollectionStatus.COMPLETED)
        )
        captive_id = asyncio.run(_seed_captive_portal(tenant_id=tenant_id))

        response = client.get("/api/v1/collections", headers=auth_header(user_id=owner_id))

    assert response.status_code == 200
    body = response.json()
    ids = [row["id"] for row in body["data"]]
    assert ids == [str(collection_id)]
    assert str(captive_id) not in ids
    # The captive-portal row must not inflate the page count either.
    assert body["meta"]["total"] == 1


def test_list_excludes_rows_predating_the_discriminator() -> None:
    """A NULL transaction_type is unclassified, not assumed to be a
    Collection — see the a762b365749e migration's unmatched-row rule."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)

        asyncio.run(
            _seed_transaction(
                tenant_id=tenant_id, status=CollectionStatus.COMPLETED, transaction_type=None
            )
        )

        response = client.get("/api/v1/collections", headers=auth_header(user_id=owner_id))

    body = response.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0


def test_list_excludes_other_tenants_collections() -> None:
    with SeededContext() as ctx:
        tenant_a = ctx.new_tenant()
        owner_a = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_a)
        tenant_b = ctx.new_tenant(name="Other Tenant")
        ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_b)

        mine = asyncio.run(
            _seed_transaction(tenant_id=tenant_a, status=CollectionStatus.COMPLETED)
        )
        theirs = asyncio.run(
            _seed_transaction(tenant_id=tenant_b, status=CollectionStatus.COMPLETED)
        )

        response = client.get("/api/v1/collections", headers=auth_header(user_id=owner_a))

    ids = [row["id"] for row in response.json()["data"]]
    assert ids == [str(mine)]
    assert str(theirs) not in ids


def test_list_status_filter_applies_inside_the_collection_subset() -> None:
    """A COMPLETED captive-portal row must not be counted or returned by
    a COMPLETED Collection filter."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)

        completed = asyncio.run(
            _seed_transaction(tenant_id=tenant_id, status=CollectionStatus.COMPLETED)
        )
        asyncio.run(_seed_transaction(tenant_id=tenant_id, status=CollectionStatus.STK_SENT))
        asyncio.run(_seed_captive_portal(tenant_id=tenant_id, status="COMPLETED"))

        response = client.get(
            "/api/v1/collections?status=COMPLETED", headers=auth_header(user_id=owner_id)
        )

    body = response.json()
    ids = [row["id"] for row in body["data"]]
    assert ids == [str(completed)]
    assert body["meta"]["total"] == 1


def test_list_pagination_totals_count_collection_rows_only() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)

        for _ in range(3):
            asyncio.run(
                _seed_transaction(tenant_id=tenant_id, status=CollectionStatus.COMPLETED)
            )
        for _ in range(4):
            asyncio.run(_seed_captive_portal(tenant_id=tenant_id))

        response = client.get(
            "/api/v1/collections?page=1&page_size=2", headers=auth_header(user_id=owner_id)
        )

    meta = response.json()["meta"]
    # 3 Collection rows over pages of 2 — the 4 captive-portal rows are
    # invisible to both the total and the page count.
    assert meta["total"] == 3
    assert meta["total_pages"] == 2
    assert meta["page_size"] == 2
    assert len(response.json()["data"]) == 2


def test_list_is_empty_for_a_tenant_with_no_collections() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)
        response = client.get("/api/v1/collections", headers=auth_header(user_id=owner_id))

    body = response.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0
    assert body["meta"]["total_pages"] == 0


def test_list_requires_authentication() -> None:
    assert client.get("/api/v1/collections").status_code == 401


def test_summary_ignores_captive_portal_rows() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)

        asyncio.run(_seed_transaction(tenant_id=tenant_id, status=CollectionStatus.COMPLETED))
        asyncio.run(_seed_captive_portal(tenant_id=tenant_id, status="COMPLETED"))
        asyncio.run(_seed_captive_portal(tenant_id=tenant_id, status="pending"))

        response = client.get(
            "/api/v1/collections/summary", headers=auth_header(user_id=owner_id)
        )

    data = response.json()["data"]
    assert data["total"] == 1
    assert data["completed"] == 1
    assert data["by_status"] == {"COMPLETED": 1}


def test_summary_ignores_rows_predating_the_discriminator() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        owner_id = ctx.new_user(role_code="TENANT_OWNER", tenant_id=tenant_id)

        asyncio.run(
            _seed_transaction(
                tenant_id=tenant_id, status=CollectionStatus.COMPLETED, transaction_type=None
            )
        )

        response = client.get(
            "/api/v1/collections/summary", headers=auth_header(user_id=owner_id)
        )

    data = response.json()["data"]
    assert data["total"] == 0
    assert data["by_status"] == {}
