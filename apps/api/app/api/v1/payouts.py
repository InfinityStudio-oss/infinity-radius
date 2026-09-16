"""Tenant payouts — thin route handlers, logic in PayoutService.

Lifecycle: TENANT_OWNER requests + confirms 2FA + can cancel their own
request. Approval is no longer a tenant-side action at all — amounts at
or under Settings.selcom_withdrawal_approval_threshold_tzs proceed
straight to Selcom once 2FA confirms; amounts over it wait for a
SUPER_ADMIN (see app/api/v1/admin_withdrawals.py), never another tenant
user. See app/services/payouts.py and docs/architecture.md.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.errors import DomainValidationError
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import FINANCE_ROLES, MANAGEMENT_ROLES, Role
from app.db.session import get_db
from app.schemas.envelope import ApiListResponse, ApiResponse, PaginationMeta
from app.schemas.finance import (
    WithdrawalCancellationRequest,
    WithdrawalCreate,
    WithdrawalDestinationCreate,
    WithdrawalDestinationRead,
    WithdrawalEventRead,
    WithdrawalLookupPreviewRequest,
    WithdrawalLookupPreviewResult,
    WithdrawalRead,
    WithdrawalRequestResult,
    WithdrawalTwoFactorConfirm,
)
from app.services.payouts import PayoutService

router = APIRouter()

require_requester = require_tenant_role(Role.TENANT_OWNER)


@router.get("", response_model=ApiListResponse[WithdrawalRead])
async def list_payouts(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*FINANCE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[WithdrawalRead]:
    service = PayoutService(db)
    items, total = await service.list_withdrawals(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[WithdrawalRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.post("", response_model=WithdrawalRequestResult, status_code=201)
async def request_payout(
    payload: WithdrawalCreate,
    ctx: TenantContext = Depends(require_requester),
    db: AsyncSession = Depends(get_db),
) -> WithdrawalRequestResult:
    service = PayoutService(db)
    withdrawal, code = await service.request_withdrawal(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        destination_id=payload.destination_id,
        amount=payload.amount,
    )
    await db.commit()
    # No ApiResponse envelope here on purpose — WithdrawalRequestResult
    # carries the one-time 2FA code, which must never be wrapped in the
    # generic response shape every other read uses (a reviewer scanning
    # response shapes for "does this ever return a secret" should be able
    # to spot this one immediately).
    return WithdrawalRequestResult(
        withdrawal=WithdrawalRead.model_validate(withdrawal), two_factor_code=code
    )


# Registered before "/{withdrawal_id}" — otherwise FastAPI tries to parse
# "destinations" as a withdrawal UUID and this route is never reached.
@router.get("/destinations", response_model=ApiListResponse[WithdrawalDestinationRead])
async def list_payout_destinations(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*FINANCE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[WithdrawalDestinationRead]:
    service = PayoutService(db)
    items, total = await service.list_destinations(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[WithdrawalDestinationRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.post(
    "/destinations", response_model=ApiResponse[WithdrawalDestinationRead], status_code=201
)
async def create_payout_destination(
    payload: WithdrawalDestinationCreate,
    ctx: TenantContext = Depends(require_tenant_role(*MANAGEMENT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalDestinationRead]:
    service = PayoutService(db)
    destination = await service.create_destination(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        label=payload.label,
        channel=payload.channel,
        destination_code=payload.destination_code,
        account_name=payload.account_name,
        account_number=payload.account_number,
        is_default=payload.is_default,
    )
    await db.commit()
    return ApiResponse(data=WithdrawalDestinationRead.model_validate(destination))


@router.post("/lookup", response_model=ApiResponse[WithdrawalLookupPreviewResult])
async def preview_payout_lookup(
    payload: WithdrawalLookupPreviewRequest,
    ctx: TenantContext = Depends(require_tenant_role(*FINANCE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalLookupPreviewResult]:
    """Read-only preview shown before the tenant confirms a withdrawal —
    never persists anything. The actual submission independently re-runs
    this same lookup server-side; this is display-only."""
    service = PayoutService(db)
    result = await service.preview_lookup(
        tenant_id=ctx.tenant_id, destination_id=payload.destination_id, amount=payload.amount
    )
    return ApiResponse(data=result)


@router.get("/{withdrawal_id}", response_model=ApiResponse[WithdrawalRead])
async def get_payout(
    withdrawal_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*FINANCE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalRead]:
    service = PayoutService(db)
    withdrawal = await service.get_withdrawal(tenant_id=ctx.tenant_id, withdrawal_id=withdrawal_id)
    return ApiResponse(data=WithdrawalRead.model_validate(withdrawal))


@router.get("/{withdrawal_id}/events", response_model=ApiListResponse[WithdrawalEventRead])
async def list_payout_events(
    withdrawal_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*FINANCE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[WithdrawalEventRead]:
    service = PayoutService(db)
    events = await service.list_events(tenant_id=ctx.tenant_id, withdrawal_id=withdrawal_id)
    return ApiListResponse(
        data=[WithdrawalEventRead.model_validate(event) for event in events],
        # Not paginated — a withdrawal's full transition history is always
        # returned in one page; there's no realistic scenario with enough
        # transitions to need it.
        meta=PaginationMeta(
            page=1, page_size=max(len(events), 1), total=len(events), total_pages=1
        ),
    )


@router.post("/{withdrawal_id}/confirm-2fa", response_model=ApiResponse[WithdrawalRead])
async def confirm_payout_two_factor(
    withdrawal_id: UUID,
    payload: WithdrawalTwoFactorConfirm,
    ctx: TenantContext = Depends(require_requester),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalRead]:
    service = PayoutService(db)
    result = await service.confirm_two_factor(
        tenant_id=ctx.tenant_id,
        withdrawal_id=withdrawal_id,
        actor_id=ctx.user.id,
        code=payload.code,
    )
    # Committed even when the code was wrong: the attempt counter (and any
    # resulting auto-cancellation) is real state that must persist —
    # see PayoutService.confirm_two_factor / TwoFactorService.verify.
    await db.commit()
    if not result.verified:
        if result.cancelled:
            raise DomainValidationError(
                "Invalid 2FA code — withdrawal cancelled after too many failed "
                "attempts or code expiry. The reserved balance has been released."
            )
        remaining = 5 - result.withdrawal.two_factor_attempts
        raise DomainValidationError(f"Invalid 2FA code — {remaining} attempt(s) remaining")
    return ApiResponse(data=WithdrawalRead.model_validate(result.withdrawal))


@router.post("/{withdrawal_id}/cancel", response_model=ApiResponse[WithdrawalRead])
async def cancel_payout(
    withdrawal_id: UUID,
    payload: WithdrawalCancellationRequest,
    ctx: TenantContext = Depends(require_requester),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalRead]:
    service = PayoutService(db)
    withdrawal = await service.cancel_withdrawal(
        tenant_id=ctx.tenant_id,
        withdrawal_id=withdrawal_id,
        actor_id=ctx.user.id,
        reason=payload.reason,
    )
    await db.commit()
    return ApiResponse(data=WithdrawalRead.model_validate(withdrawal))
