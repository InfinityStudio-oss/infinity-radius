"""Tenant wallet accounting — ledger_entries is the financial source of
truth, tenant_wallets a summarized cache (see app/services/wallet.py).

Drives WalletService directly via a one-shot `asyncio.run(...)` per test,
the same pattern test_captive_portal_payments.py uses for
CaptivePortalService — a synchronous test body, a single throwaway event
loop, never a persistent async fixture (see tests/db_fixtures.py's module
docstring for why: a second asyncpg engine touched from a different loop
corrupts the pool on Windows).
"""

import asyncio
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.enums import LedgerDirection, WalletBucket
from app.core.errors import DomainValidationError
from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.commercial_terms import CommercialTermsService
from app.services.wallet import WalletService
from tests.auth_helpers import auth_header
from tests.db_fixtures import SeededContext

client = TestClient(app)


async def _process_collection(tenant_id: UUID, gross_amount: str) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        result = await WalletService(db).process_collection(
            tenant_id=tenant_id,
            gross_amount=Decimal(gross_amount),
            reference_type="test",
            reference_id=None,
            description="test collection",
        )
        await db.commit()
        return {
            "platform_fee": str(result.platform_fee),
            "tenant_share": str(result.tenant_share),
            "pending_balance_tzs": str(result.wallet.pending_balance_tzs),
        }


async def _set_commission_rate(tenant_id: UUID, rate: str) -> None:
    async with AsyncSessionLocal() as db:
        await CommercialTermsService(db).set_commission_rate(
            tenant_id=tenant_id, commission_rate_percent=Decimal(rate), actor_id=None
        )
        await db.commit()


def test_process_collection_fails_closed_with_no_commercial_terms() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()

        with pytest.raises(DomainValidationError):
            asyncio.run(_process_collection(tenant_id, "1000.00"))


def test_process_collection_splits_gross_using_tenant_rate() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        asyncio.run(_set_commission_rate(tenant_id, "10.00"))

        result = asyncio.run(_process_collection(tenant_id, "1000.00"))

    assert result["platform_fee"] == "100.00"
    assert result["tenant_share"] == "900.00"
    assert result["pending_balance_tzs"] == "900.00"


def test_process_collection_fee_split_always_sums_to_gross() -> None:
    """platform_fee is quantized first, tenant_share = gross - platform_fee
    by subtraction — the two must always sum exactly to gross, even for a
    rate that doesn't divide evenly."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        asyncio.run(_set_commission_rate(tenant_id, "12.50"))

        result = asyncio.run(_process_collection(tenant_id, "999.99"))

    fee = Decimal(result["platform_fee"])
    share = Decimal(result["tenant_share"])
    assert fee + share == Decimal("999.99")


async def _create_adjustment(
    tenant_id: UUID,
    *,
    bucket: WalletBucket,
    direction: LedgerDirection,
    amount: str,
    reason: str,
    actor_id: UUID,
) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        service = WalletService(db)
        entry = await service.create_adjustment(
            tenant_id=tenant_id,
            wallet_bucket=bucket,
            direction=direction,
            amount=Decimal(amount),
            reason=reason,
            actor_id=actor_id,
        )
        await db.commit()
        return {"balance_after": str(entry.balance_after), "entry_type": entry.entry_type}


def test_adjustment_requires_a_reason() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        actor_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        with pytest.raises(DomainValidationError):
            asyncio.run(
                _create_adjustment(
                    tenant_id,
                    bucket=WalletBucket.AVAILABLE,
                    direction=LedgerDirection.CREDIT,
                    amount="500.00",
                    reason="   ",
                    actor_id=actor_id,
                )
            )


def test_adjustment_credits_a_bucket_and_writes_an_immutable_entry() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        actor_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        result = asyncio.run(
            _create_adjustment(
                tenant_id,
                bucket=WalletBucket.AVAILABLE,
                direction=LedgerDirection.CREDIT,
                amount="500.00",
                reason="Manual correction for a support ticket",
                actor_id=actor_id,
            )
        )

    assert result["entry_type"] == "ADJUSTMENT"
    assert result["balance_after"] == "500.00"


def test_adjustment_cannot_take_a_bucket_negative() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        actor_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)

        with pytest.raises(DomainValidationError):
            asyncio.run(
                _create_adjustment(
                    tenant_id,
                    bucket=WalletBucket.AVAILABLE,
                    direction=LedgerDirection.DEBIT,
                    amount="100.00",
                    reason="Should fail — wallet has nothing available",
                    actor_id=actor_id,
                )
            )


def test_wallet_adjustment_endpoint_requires_super_admin() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        tenant_admin_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            f"/api/v1/tenants/{tenant_id}/wallet/adjustments",
            headers=auth_header(user_id=tenant_admin_id),
            json={
                "wallet_bucket": "available",
                "direction": "credit",
                "amount": "500.00",
                "reason": "attempted by a non-super-admin",
            },
        )

    assert response.status_code == 403


def test_wallet_adjustment_endpoint_never_accepts_a_raw_balance_field() -> None:
    """The only shape WalletAdjustmentRequest accepts is a signed delta
    against a named bucket — a "balance" field is simply not part of the
    schema, so extra/unknown input like that is ignored, never applied."""
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        admin_id = ctx.new_user(role_code="SUPER_ADMIN", tenant_id=None)
        tenant_admin_id = ctx.new_user(role_code="TENANT_ADMIN", tenant_id=tenant_id)

        response = client.post(
            f"/api/v1/tenants/{tenant_id}/wallet/adjustments",
            headers=auth_header(user_id=admin_id),
            json={
                "wallet_bucket": "available",
                "direction": "credit",
                "amount": "250.00",
                "reason": "Reconciliation adjustment",
                "balance": "999999.00",
            },
        )
        assert response.status_code == 201
        assert response.json()["data"]["entry_type"] == "ADJUSTMENT"
        assert response.json()["data"]["actor_id"] == str(admin_id)

        wallet_response = client.get(
            "/api/v1/wallet", headers=auth_header(user_id=tenant_admin_id)
        )

    assert wallet_response.json()["data"]["available_balance_tzs"] == "250.00"


async def _settle_pending(tenant_id: UUID, amount: str | None) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        service = WalletService(db)
        wallet = await service.get_or_create_wallet(tenant_id=tenant_id)
        await service.settle_pending(
            tenant_id=tenant_id,
            amount=Decimal(amount) if amount is not None else None,
            batch_reference="TEST-BATCH-1",
        )
        await db.refresh(wallet)
        await db.commit()
        return {
            "pending": str(wallet.pending_balance_tzs),
            "available": str(wallet.available_balance_tzs),
        }


def test_settle_pending_moves_the_whole_balance_to_available_by_default() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        asyncio.run(_set_commission_rate(tenant_id, "10.00"))
        asyncio.run(_process_collection(tenant_id, "1000.00"))

        result = asyncio.run(_settle_pending(tenant_id, None))

    assert result["pending"] == "0.00"
    assert result["available"] == "900.00"


def test_settle_pending_rejects_more_than_the_current_pending_balance() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        asyncio.run(_set_commission_rate(tenant_id, "10.00"))
        asyncio.run(_process_collection(tenant_id, "1000.00"))

        with pytest.raises(DomainValidationError):
            asyncio.run(_settle_pending(tenant_id, "5000.00"))


async def _withdrawal_lifecycle(tenant_id: UUID) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        service = WalletService(db)
        wallet = await service.get_or_create_wallet(tenant_id=tenant_id)
        await service.reserve_for_withdrawal(tenant_id=tenant_id, amount=Decimal("400.00"))
        await service.complete_disbursement(tenant_id=tenant_id, amount=Decimal("400.00"))
        await db.refresh(wallet)
        await db.commit()
        return {
            "available": str(wallet.available_balance_tzs),
            "reserved": str(wallet.reserved_balance_tzs),
            "total_disbursed": str(wallet.total_disbursed_tzs),
        }


async def _reverse_disbursement(tenant_id: UUID) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        service = WalletService(db)
        wallet = await service.get_or_create_wallet(tenant_id=tenant_id)
        await service.reverse_disbursement(tenant_id=tenant_id, amount=Decimal("400.00"))
        await db.refresh(wallet)
        await db.commit()
        return {
            "available": str(wallet.available_balance_tzs),
            "total_disbursed": str(wallet.total_disbursed_tzs),
        }


def test_reserve_and_complete_disbursement_moves_available_to_total_disbursed() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        asyncio.run(_set_commission_rate(tenant_id, "10.00"))
        asyncio.run(_process_collection(tenant_id, "1000.00"))
        asyncio.run(_settle_pending(tenant_id, None))  # 900.00 now available

        result = asyncio.run(_withdrawal_lifecycle(tenant_id))

    assert result["available"] == "500.00"
    assert result["reserved"] == "0.00"
    assert result["total_disbursed"] == "400.00"


def test_reverse_disbursement_moves_total_disbursed_back_to_available() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        asyncio.run(_set_commission_rate(tenant_id, "10.00"))
        asyncio.run(_process_collection(tenant_id, "1000.00"))
        asyncio.run(_settle_pending(tenant_id, None))
        asyncio.run(_withdrawal_lifecycle(tenant_id))

        result = asyncio.run(_reverse_disbursement(tenant_id))

    assert result["available"] == "900.00"
    assert result["total_disbursed"] == "0.00"


async def _record_refund_and_reversal(tenant_id: UUID) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        service = WalletService(db)
        wallet = await service.get_or_create_wallet(tenant_id=tenant_id)
        await service.record_reversal(tenant_id=tenant_id, amount=Decimal("100.00"))
        await service.settle_pending(
            tenant_id=tenant_id, amount=None, batch_reference="TEST-BATCH-2"
        )
        await service.record_refund(tenant_id=tenant_id, amount=Decimal("50.00"))
        await db.refresh(wallet)
        await db.commit()
        return {
            "pending": str(wallet.pending_balance_tzs),
            "available": str(wallet.available_balance_tzs),
        }


def test_reversal_and_refund_debit_the_expected_buckets() -> None:
    with SeededContext() as ctx:
        tenant_id = ctx.new_tenant()
        asyncio.run(_set_commission_rate(tenant_id, "10.00"))
        asyncio.run(_process_collection(tenant_id, "1000.00"))  # +900.00 pending

        result = asyncio.run(_record_refund_and_reversal(tenant_id))

    # 900 pending - 100 reversed = 800 settled to available, then -50 refund = 750
    assert result["pending"] == "0.00"
    assert result["available"] == "750.00"
