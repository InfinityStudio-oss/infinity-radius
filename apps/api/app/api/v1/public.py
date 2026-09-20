"""Unauthenticated endpoints reached by end-user-facing surfaces — the WiFi
captive portal. A hotspot customer never has a Supabase session, so these
routes carry no auth dependency.

Scoping is entirely through the signed `router` token a MikroTik hotspot's
login redirect carries — never a tenant_id, and never a raw/unsigned
router id. See app/core/router_token.py for why: the token is
authenticated + encrypted (Fernet), so a client can't forge one for a
router it wasn't issued, and the router UUID inside isn't even visible.
The backend resolves router token -> router -> tenant itself; the tenant
is never a value the client supplies or can read back out.

Payment status polling is scoped the same way but by a *transaction*
token (app/core/transaction_token.py) — never the transaction's database
id, so a client can't enumerate or read anyone else's private transaction.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainValidationError
from app.core.router_token import resolve_router_token
from app.db.session import get_db
from app.repositories.network import LocationRepository, RouterRepository
from app.schemas.captive_portal import (
    CaptivePortalBrandingRead,
    CaptivePortalPackageRead,
    CaptivePortalPaymentInitiateRequest,
    CaptivePortalPaymentInitiateResult,
    CaptivePortalPaymentStatusResult,
    CaptivePortalResolveResult,
    CaptivePortalSessionRequest,
    CaptivePortalSessionResult,
)
from app.schemas.common import ResourceListResponse
from app.services.captive_portal import CaptivePortalService
from app.services.captive_session import (
    CaptivePortalSessionService,
    CaptiveSessionError,
)
from app.services.packages import PackageService

router = APIRouter()


@router.get("/captive-portal/resolve", response_model=CaptivePortalResolveResult)
async def resolve_captive_portal(
    router_token: str = Query(
        ..., alias="router", description="Signed router token from the hotspot redirect"
    ),
    mac: str | None = Query(default=None, description="Client MAC address"),
    dst: str | None = Query(default=None, description="Originally requested destination URL"),
    login: str | None = Query(
        default=None, description="Router's local hotspot login endpoint ($(link-login-only))"
    ),
    db: AsyncSession = Depends(get_db),
) -> CaptivePortalResolveResult:
    router_id = resolve_router_token(router_token)
    if router_id is None:
        return CaptivePortalResolveResult(status="invalid_token", mac=mac, dst=dst)

    router_repo = RouterRepository(db)
    # tenant_id=None: this lookup is deliberately not tenant-scoped — the
    # token is the only thing establishing which router (and therefore
    # which tenant) this request is about.
    router_row = await router_repo.get_by_id(tenant_id=None, id=router_id)
    if router_row is None:
        return CaptivePortalResolveResult(status="router_not_found", mac=mac, dst=dst)

    site_name = None
    if router_row.location_id is not None:
        location_repo = LocationRepository(db)
        location = await location_repo.get_by_id(
            tenant_id=router_row.tenant_id, id=router_row.location_id
        )
        site_name = location.name if location is not None else None

    return CaptivePortalResolveResult(
        status="ok",
        router_name=router_row.name,
        site_name=site_name,
        mac=mac,
        dst=dst,
        login_url=login,
    )


@router.get("/captive-portal/branding", response_model=CaptivePortalBrandingRead)
async def get_captive_portal_branding(
    router_token: str = Query(
        ..., alias="router", description="Signed router token from the hotspot redirect"
    ),
    db: AsyncSession = Depends(get_db),
) -> CaptivePortalBrandingRead:
    router_id = resolve_router_token(router_token)
    if router_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid router token")

    service = CaptivePortalService(db)
    tenant_id = await service.resolve_tenant_id_for_router(router_id)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Router not found")
    return await service.get_branding(tenant_id=tenant_id)


@router.get("/captive-portal/packages", response_model=ResourceListResponse)
async def get_captive_portal_packages(
    router_token: str = Query(
        ..., alias="router", description="Signed router token from the hotspot redirect"
    ),
    db: AsyncSession = Depends(get_db),
) -> ResourceListResponse:
    router_id = resolve_router_token(router_token)
    if router_id is None:
        return ResourceListResponse(items=[], total=0, status="not_configured")

    router_repo = RouterRepository(db)
    router_row = await router_repo.get_by_id(tenant_id=None, id=router_id)
    if router_row is None:
        return ResourceListResponse(items=[], total=0, status="not_configured")

    packages = await PackageService(db).list_active_packages(tenant_id=router_row.tenant_id)
    items = [
        CaptivePortalPackageRead.model_validate(package, from_attributes=True).model_dump(
            mode="json"
        )
        for package in packages
    ]
    return ResourceListResponse(items=items, total=len(items), status="ok")


@router.post(
    "/captive-portal/session",
    response_model=CaptivePortalSessionResult,
    status_code=201,
)
async def create_captive_portal_session(
    payload: CaptivePortalSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> CaptivePortalSessionResult:
    """Exchanges a long-lived, site-wide router token for a SHORT-LIVED,
    single-use payment intent token.

    The router token identifies a site and lives in every router's hotspot
    config, so it is effectively public to anyone who has associated with
    that AP. It must therefore not be what authorizes spending money. This
    endpoint is the boundary between the two: the tenant is resolved from
    the router server-side and recorded on the session, and the token
    handed back expires and can only be spent once.
    """
    router_id = resolve_router_token(payload.router)
    if router_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid router token")

    service = CaptivePortalSessionService(db)
    try:
        token, session = await service.issue(
            router_id=router_id, mac_address=payload.mac_address
        )
    except CaptiveSessionError as exc:
        # One opaque failure for every reason (unknown router, signing key
        # unset) so the endpoint cannot be probed for which is the case.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment sessions are unavailable on this network.",
        ) from exc

    await db.commit()
    return CaptivePortalSessionResult(intent_token=token, expires_at=session.expires_at)


@router.post(
    "/captive-portal/payments/initiate",
    response_model=CaptivePortalPaymentInitiateResult,
    status_code=201,
)
async def initiate_captive_portal_payment(
    payload: CaptivePortalPaymentInitiateRequest,
    db: AsyncSession = Depends(get_db),
) -> CaptivePortalPaymentInitiateResult:
    """Starts one payment attempt.

    The request carries an intent token, a package and a phone number, and
    nothing financial — see CaptivePortalPaymentInitiateRequest for why
    that is enforced by the model's shape rather than by validation.
    """
    service = CaptivePortalService(db)
    try:
        result = await service.initiate_payment(
            intent_token=payload.intent_token,
            package_id=payload.package_id,
            phone=payload.phone,
        )
    except DomainValidationError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.message
        ) from exc

    await db.commit()
    return result


@router.get(
    "/captive-portal/payments/status", response_model=CaptivePortalPaymentStatusResult
)
async def get_captive_portal_payment_status(
    token: str = Query(..., description="Signed public transaction token"),
    db: AsyncSession = Depends(get_db),
) -> CaptivePortalPaymentStatusResult:
    return await CaptivePortalService(db).get_payment_status(token=token)
