"""Tenant-facing Selcom Mobile Checkout Collection — initiate a customer
STK push and check its status. Own router, separate from the read-only
historical list at app/api/v1/payments.py (kept as-is)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.enums import COLLECTION_TERMINAL_STATUSES, CollectionStatus, TransactionType
from app.core.errors import NotFoundError
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import FRONTLINE_ROLES
from app.db.session import get_db
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.schemas.finance import CollectionCreate, CollectionSummaryRead, TransactionRead
from app.services.collections import CollectionService

router = APIRouter()

# Card groupings for the tenant dashboard. Deliberately derived from the
# same CollectionStatus/COLLECTION_TERMINAL_STATUSES definitions the
# reconciliation logic uses, so a status added there can never silently
# vanish from the dashboard's totals — anything unrecognised still lands
# in `total` and in `by_status`.
_IN_PROGRESS_STATUSES = frozenset(
    {
        CollectionStatus.CREATED.value,
        CollectionStatus.STK_SENT.value,
        CollectionStatus.PENDING.value,
        CollectionStatus.INPROGRESS.value,
    }
)
_ATTENTION_STATUSES = frozenset(
    {CollectionStatus.REQUIRES_REVIEW.value, CollectionStatus.AMBIGUOUS.value}
)
_FAILED_STATUSES = frozenset(
    status.value
    for status in COLLECTION_TERMINAL_STATUSES
    if status is not CollectionStatus.COMPLETED
)


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


@router.get("", response_model=ApiListResponse[TransactionRead])
async def list_collections(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[TransactionRead]:
    """This tenant's Collection history.

    Deliberately NOT the generic /payments list: `transactions` is shared
    with captive-portal payments, so scoping happens server-side on the
    explicit transaction_type discriminator. Search/sort/status filtering
    and the `total` used for pagination are all evaluated inside that
    subset, so a captive-portal row can never appear here or inflate a
    page count. Rows predating the discriminator (NULL) are excluded
    rather than assumed — see the a762b365749e migration.
    """
    service = CollectionService(db)
    items, total = await service.repo.list_by_type_paginated(
        tenant_id=ctx.tenant_id,
        transaction_type=TransactionType.COLLECTION.value,
        params=params,
    )
    return ApiListResponse(
        data=[TransactionRead.from_transaction(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/summary", response_model=ApiResponse[CollectionSummaryRead])
async def get_collection_summary(
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CollectionSummaryRead]:
    """Exact per-status totals for this tenant's Collections.

    MUST stay declared above GET /{transaction_id}: FastAPI matches routes
    in declaration order, so the dynamic route would otherwise swallow
    "/summary" and fail trying to parse it as a UUID.
    """
    service = CollectionService(db)
    counts = await service.repo.count_by_status(
        tenant_id=ctx.tenant_id, transaction_type=TransactionType.COLLECTION.value
    )

    def total_for(statuses: frozenset[str]) -> int:
        return sum(count for status, count in counts.items() if status in statuses)

    return ApiResponse(
        data=CollectionSummaryRead(
            total=sum(counts.values()),
            completed=counts.get(CollectionStatus.COMPLETED.value, 0),
            in_progress=total_for(_IN_PROGRESS_STATUSES),
            requires_attention=total_for(_ATTENTION_STATUSES),
            failed=total_for(_FAILED_STATUSES),
            by_status=counts,
        )
    )


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
