"""Super Admin withdrawal review — the only place a withdrawal above
Settings.selcom_withdrawal_approval_threshold_tzs can be approved or
rejected. SUPER_ADMIN only; never a tenant user, per app/services/payouts.py.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
