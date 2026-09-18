"""Super Admin withdrawal review — the only place a withdrawal above
Settings.selcom_withdrawal_approval_threshold_tzs can be approved or
rejected. SUPER_ADMIN only; never a tenant user, per app/services/payouts.py.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import Role
from app.core.security import AuthenticatedUser, require_role
from app.db.session import get_db
from app.schemas.envelope import ApiListResponse, ApiResponse, PaginationMeta
from app.schemas.finance import (
    WithdrawalApprovalRequest,
    WithdrawalRead,
    WithdrawalRejectionRequest,
)
from app.services.payouts import PayoutService

router = APIRouter()

require_super_admin = require_role(Role.SUPER_ADMIN)


@router.get("", response_model=ApiListResponse[WithdrawalRead])
async def list_pending_withdrawals(
    _: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[WithdrawalRead]:
    service = PayoutService(db)
    items = await service.list_pending_super_admin_approval()
    return ApiListResponse(
        data=[WithdrawalRead.model_validate(item) for item in items],
        meta=PaginationMeta(
            page=1, page_size=max(len(items), 1), total=len(items), total_pages=1 if items else 0
        ),
    )


# Registered before "/{withdrawal_id}" — otherwise FastAPI tries to parse
# "all" as a UUID and this route is never reached (the same fix
# app/api/v1/payouts.py already applied for "/destinations").
@router.get("/all", response_model=ApiListResponse[WithdrawalRead])
async def list_all_withdrawals(
    params: ListParams = Depends(list_params),
    _: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[WithdrawalRead]:
    """The broader operational view — every tenant, every status,
    paginated/searchable/filterable (`?status=PROCESSING`,
    `?status=AMBIGUOUS`, etc.) — distinct from the narrower
    GET "" approval queue above. Read-only; no action is exposed here
    beyond what {withdrawal_id}/approve|reject|requery already allow."""
    service = PayoutService(db)
    items, total = await service.list_all_for_super_admin(params=params)
    return ApiListResponse(
        data=[WithdrawalRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/{withdrawal_id}", response_model=ApiResponse[WithdrawalRead])
async def get_withdrawal_for_review(
    withdrawal_id: UUID,
    _: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalRead]:
    service = PayoutService(db)
    withdrawal = await service.get_withdrawal_for_super_admin(withdrawal_id=withdrawal_id)
    return ApiResponse(data=WithdrawalRead.model_validate(withdrawal))


@router.post("/{withdrawal_id}/approve", response_model=ApiResponse[WithdrawalRead])
async def approve_withdrawal(
    withdrawal_id: UUID,
    payload: WithdrawalApprovalRequest,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalRead]:
    service = PayoutService(db)
    withdrawal = await service.approve_withdrawal(
        withdrawal_id=withdrawal_id, actor_id=user.id, notes=payload.notes
    )
    await db.commit()
    return ApiResponse(data=WithdrawalRead.model_validate(withdrawal))


@router.post("/{withdrawal_id}/reject", response_model=ApiResponse[WithdrawalRead])
async def reject_withdrawal(
    withdrawal_id: UUID,
    payload: WithdrawalRejectionRequest,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalRead]:
    service = PayoutService(db)
    withdrawal = await service.reject_withdrawal(
        withdrawal_id=withdrawal_id, actor_id=user.id, reason=payload.reason
    )
    await db.commit()
    return ApiResponse(data=WithdrawalRead.model_validate(withdrawal))


@router.post("/{withdrawal_id}/requery", response_model=ApiResponse[WithdrawalRead])
async def requery_withdrawal(
    withdrawal_id: UUID,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalRead]:
    """The ONE safe manual action for a PROCESSING/AMBIGUOUS withdrawal —
    an authenticated GET /v1/transaction/query against Selcom with this
    withdrawal's own idempotency_key, exactly what the periodic Beat sweep
    and the disbursement webhook both already do (see
    PayoutService.reconcile_withdrawal). There is deliberately no
    "resubmit"/"resend payout" action anywhere in this API — manually
    retrying transaction/process is never safe and this platform never
    exposes a way to do it. Useful when an operator wants an immediate
    answer instead of waiting up to 120s for the next scheduled sweep."""
    service = PayoutService(db)
    withdrawal = await service.reconcile_withdrawal(withdrawal_id=withdrawal_id)
    await db.commit()
    return ApiResponse(data=WithdrawalRead.model_validate(withdrawal))
