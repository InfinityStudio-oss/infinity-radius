"""Tenants — platform-wide listing is super-admin only; a tenant's own
staff can see only their own tenant's record via /tenants/me."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, get_tenant_context
from app.core.errors import NotFoundError
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import Role
from app.core.security import AuthenticatedUser, require_role
from app.db.session import get_db
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.schemas.finance import (
    LedgerEntryRead,
    TenantCommercialTermsCreate,
    TenantCommercialTermsRead,
    TenantSettlementConfigCreate,
    TenantSettlementConfigRead,
    WalletAdjustmentRequest,
    WithdrawalRead,
    WithdrawalReversalRequest,
)
from app.schemas.tenancy import TenantRead
from app.services.commercial_terms import CommercialTermsService
from app.services.payouts import PayoutService
from app.services.settlement_config import SettlementConfigService
from app.services.tenants import TenantService
from app.services.wallet import WalletService

router = APIRouter()

require_super_admin = require_role(Role.SUPER_ADMIN)


async def _require_existing_tenant(tenant_id: UUID, db: AsyncSession) -> None:
    if await TenantService(db).repo.get_by_id(tenant_id=None, id=tenant_id) is None:
        raise NotFoundError("Tenant not found")


@router.get("", response_model=ApiListResponse[TenantRead])
async def list_tenants(
    params: ListParams = Depends(list_params),
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[TenantRead]:
    service = TenantService(db)
    items, total = await service.list_all(params=params)
    return ApiListResponse(
        data=[TenantRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/me", response_model=ApiResponse[TenantRead])
async def get_my_tenant(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantRead]:
    service = TenantService(db)
    tenant = await service.get(tenant_id=ctx.tenant_id)
    return ApiResponse(data=TenantRead.model_validate(tenant))


@router.get("/{tenant_id}", response_model=ApiResponse[TenantRead])
async def get_tenant(
    tenant_id: UUID,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantRead]:
    service = TenantService(db)
    tenant = await service.get(tenant_id=tenant_id)
    return ApiResponse(data=TenantRead.model_validate(tenant))


@router.get(
    "/{tenant_id}/commercial-terms", response_model=ApiResponse[TenantCommercialTermsRead | None]
)
async def get_commercial_terms(
    tenant_id: UUID,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantCommercialTermsRead | None]:
    await _require_existing_tenant(tenant_id, db)
    terms = await CommercialTermsService(db).get_active(tenant_id=tenant_id)
    return ApiResponse(
        data=TenantCommercialTermsRead.model_validate(terms) if terms is not None else None
    )


@router.post(
    "/{tenant_id}/commercial-terms",
    response_model=ApiResponse[TenantCommercialTermsRead],
    status_code=201,
)
async def set_commercial_terms(
    tenant_id: UUID,
    payload: TenantCommercialTermsCreate,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantCommercialTermsRead]:
    """Versions the tenant's platform commission rate — never a hard-coded
    global default. The previous active rate (if any) is deactivated, not
    overwritten, so the full history is retained."""
    await _require_existing_tenant(tenant_id, db)
    terms = await CommercialTermsService(db).set_commission_rate(
        tenant_id=tenant_id,
        commission_rate_percent=payload.commission_rate_percent,
        actor_id=user.id,
        notes=payload.notes,
    )
    await db.commit()
    return ApiResponse(data=TenantCommercialTermsRead.model_validate(terms))


@router.post(
    "/{tenant_id}/wallet/adjustments",
    response_model=ApiResponse[LedgerEntryRead],
    status_code=201,
)
async def create_wallet_adjustment(
    tenant_id: UUID,
    payload: WalletAdjustmentRequest,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LedgerEntryRead]:
    """The only way any admin can correct a tenant's wallet — a signed
    delta against one bucket, with a mandatory reason, recorded as an
    immutable ADJUSTMENT ledger entry attributed to this actor. There is
    no endpoint anywhere that accepts a raw new balance."""
    await _require_existing_tenant(tenant_id, db)
    entry = await WalletService(db).create_adjustment(
        tenant_id=tenant_id,
        wallet_bucket=payload.wallet_bucket,
        direction=payload.direction,
        amount=payload.amount,
        reason=payload.reason,
        actor_id=user.id,
    )
    await db.commit()
    return ApiResponse(data=LedgerEntryRead.model_validate(entry))


@router.get(
    "/{tenant_id}/settlement-config", response_model=ApiResponse[TenantSettlementConfigRead | None]
)
async def get_settlement_config(
    tenant_id: UUID,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantSettlementConfigRead | None]:
    await _require_existing_tenant(tenant_id, db)
    config = await SettlementConfigService(db).get_active(tenant_id=tenant_id)
    return ApiResponse(
        data=TenantSettlementConfigRead.model_validate(config) if config is not None else None
    )


@router.post(
    "/{tenant_id}/settlement-config",
    response_model=ApiResponse[TenantSettlementConfigRead],
    status_code=201,
)
async def set_settlement_config(
    tenant_id: UUID,
    payload: TenantSettlementConfigCreate,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantSettlementConfigRead]:
    """Switches which disbursement architecture mode applies to this
    tenant — see app.core.enums.SettlementMode. Never assumed: a tenant
    with no row here is DIRECT_MERCHANT_SETTLEMENT (Infinity Radius does
    not hold its funds) until a super admin explicitly sets it otherwise."""
    await _require_existing_tenant(tenant_id, db)
    config = await SettlementConfigService(db).set_mode(
        tenant_id=tenant_id, mode=payload.mode, actor_id=user.id, notes=payload.notes
    )
    await db.commit()
    return ApiResponse(data=TenantSettlementConfigRead.model_validate(config))


@router.post(
    "/{tenant_id}/withdrawals/{withdrawal_id}/reverse",
    response_model=ApiResponse[WithdrawalRead],
)
async def reverse_tenant_withdrawal(
    tenant_id: UUID,
    withdrawal_id: UUID,
    payload: WithdrawalReversalRequest,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WithdrawalRead]:
    """Reverses an already-SUCCESS'd disbursement — exceptional/rare (a
    bad account number, a provider recall). SUPER_ADMIN only, same
    justification as the wallet-adjustment endpoint above: this moves
    money back into a tenant's wallet outside the normal request/approve
    flow, so it needs the same platform-level authority and mandatory
    reason."""
    await _require_existing_tenant(tenant_id, db)
    withdrawal = await PayoutService(db).reverse_withdrawal(
        tenant_id=tenant_id, withdrawal_id=withdrawal_id, actor_id=user.id, reason=payload.reason
    )
    await db.commit()
    return ApiResponse(data=WithdrawalRead.model_validate(withdrawal))
