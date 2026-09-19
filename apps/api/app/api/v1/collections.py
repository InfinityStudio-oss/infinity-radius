"""Tenant-facing Selcom Mobile Checkout Collection — initiate a customer
STK push and check its status. Own router, separate from the read-only
historical list at app/api/v1/payments.py (kept as-is)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.errors import NotFoundError
from app.core.roles import FRONTLINE_ROLES
from app.db.session import get_db
from app.schemas.envelope import ApiResponse
from app.schemas.finance import CollectionCreate, TransactionRead
from app.services.collections import CollectionService

router = APIRouter()


@router.post("", response_model=ApiResponse[TransactionRead])
async def initiate_collection(
    payload: CollectionCreate,
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TransactionRead]:
    """Creates one Collection order and immediately requests the STK/
    wallet-pull push. A 200 response only ever means Selcom accepted the
    request for processing — never that the customer paid; poll
    GET /{id} or wait for the tenant's own transaction list to update
    once the webhook/reconciliation resolves it."""
    service = CollectionService(db)
    transaction = await service.initiate_collection(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        amount=payload.amount,
        currency=payload.currency,
        phone=payload.phone,
        customer_id=payload.customer_id,
        description=payload.description,
    )
    await db.commit()
    return ApiResponse(data=TransactionRead.from_transaction(transaction))


@router.get("/{transaction_id}", response_model=ApiResponse[TransactionRead])
async def get_collection(
    transaction_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TransactionRead]:
    """Read-only status check — reflects whatever the last webhook/
    reconciliation sweep found; never triggers a fresh provider query
    itself (see Part G of the production-activation task: no manual
    force-reconciliation from a polling endpoint)."""
    service = CollectionService(db)
    transaction = await service.repo.get_by_id(tenant_id=ctx.tenant_id, id=transaction_id)
    if transaction is None:
        raise NotFoundError("Collection transaction not found")
    return ApiResponse(data=TransactionRead.from_transaction(transaction))
