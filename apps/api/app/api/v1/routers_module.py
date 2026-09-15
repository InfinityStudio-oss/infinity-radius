"""MikroTik routers — mounted at /api/v1/routers. Filename avoids the
`routers.py` name to not shadow the `router = APIRouter()` convention
used throughout this package."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import NETWORK_ROLES, TENANT_STAFF_ROLES
from app.db.session import get_db
from app.integrations.network_agent.schemas import TestConnectionResult
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.schemas.network import RouterCreate, RouterHealthRead, RouterRead
from app.schemas.router_provisioning import (
    HotspotConfigResult,
    NetworkConfigRead,
    NetworkConfigRequest,
    PublicRouterTokenResult,
    RadiusConfigResult,
    WalledGardenResult,
    WireGuardConfigResult,
)
from app.services.network_routers import RouterService
from app.services.router_provisioning import RouterProvisioningService

router = APIRouter()


@router.get("", response_model=ApiListResponse[RouterRead])
async def list_routers(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[RouterRead]:
    service = RouterService(db)
    items, total = await service.list(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[RouterRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )



# Registered before "/{router_id}" — otherwise FastAPI tries to parse
# "health" as a router UUID and this route is never reached (same class of
# bug as payouts.py's /destinations — see that file's history).
@router.get("/health", response_model=ApiResponse[list[RouterHealthRead]])
async def get_routers_health(
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[RouterHealthRead]]:
    service = RouterService(db)
    return ApiResponse(data=await service.health(tenant_id=ctx.tenant_id))


@router.get("/{router_id}", response_model=ApiResponse[RouterRead])
async def get_router(
    router_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RouterRead]:
    service = RouterService(db)
    router_obj = await service.get(tenant_id=ctx.tenant_id, router_id=router_id)
    return ApiResponse(data=RouterRead.model_validate(router_obj))


@router.post("", response_model=ApiResponse[RouterRead], status_code=201)
async def create_router(
    payload: RouterCreate,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RouterRead]:
    service = RouterService(db)
    router_obj = await service.create(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        name=payload.name,
        location_id=payload.location_id,
        model=payload.model,
        management_ip=payload.management_ip,
        mac_address=payload.mac_address,
    )
    await db.commit()
    return ApiResponse(data=RouterRead.model_validate(router_obj))


@router.post("/{router_id}/test-connection", response_model=ApiResponse[TestConnectionResult])
async def test_router_connection(
    router_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TestConnectionResult]:
    service = RouterService(db)
    result = await service.test_connection(tenant_id=ctx.tenant_id, router_id=router_id)
    return ApiResponse(data=result)


# --- Add Router Wizard (steps 3-7 + 9; step 1-2 is the plain create above,
# step 8 is test-connection above) ---


@router.put(
    "/{router_id}/provisioning/network-config", response_model=ApiResponse[NetworkConfigRead]
)
async def set_router_network_config(
    router_id: UUID,
    payload: NetworkConfigRequest,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[NetworkConfigRead]:
    service = RouterProvisioningService(db)
    result = await service.set_network_config(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        router_id=router_id,
        network_cidr=str(payload.network_cidr),
        gateway_ip=str(payload.gateway_ip),
        dns_servers=[str(ip) for ip in payload.dns_servers],
    )
    await db.commit()
    return ApiResponse(data=result)


@router.post(
    "/{router_id}/provisioning/wireguard", response_model=ApiResponse[WireGuardConfigResult]
)
async def generate_router_wireguard_config(
    router_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WireGuardConfigResult]:
    service = RouterProvisioningService(db)
    result = await service.generate_wireguard_config(
        tenant_id=ctx.tenant_id, actor_id=ctx.user.id, router_id=router_id
    )
    await db.commit()
    return ApiResponse(data=result)


@router.post(
    "/{router_id}/provisioning/radius", response_model=ApiResponse[RadiusConfigResult]
)
async def generate_router_radius_config(
    router_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RadiusConfigResult]:
    service = RouterProvisioningService(db)
    result = await service.generate_radius_config(
        tenant_id=ctx.tenant_id, actor_id=ctx.user.id, router_id=router_id
    )
    await db.commit()
    return ApiResponse(data=result)


@router.post(
    "/{router_id}/provisioning/hotspot", response_model=ApiResponse[HotspotConfigResult]
)
async def generate_router_hotspot_config(
    router_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[HotspotConfigResult]:
    service = RouterProvisioningService(db)
    result = await service.generate_hotspot_config(
        tenant_id=ctx.tenant_id, actor_id=ctx.user.id, router_id=router_id
    )
    await db.commit()
    return ApiResponse(data=result)


@router.post(
    "/{router_id}/provisioning/walled-garden", response_model=ApiResponse[WalledGardenResult]
)
async def generate_router_walled_garden(
    router_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WalledGardenResult]:
    service = RouterProvisioningService(db)
    result = await service.generate_walled_garden_rules(
        tenant_id=ctx.tenant_id, actor_id=ctx.user.id, router_id=router_id
    )
    await db.commit()
    return ApiResponse(data=result)


@router.get(
    "/{router_id}/provisioning/public-token", response_model=ApiResponse[PublicRouterTokenResult]
)
async def get_router_public_token(
    router_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PublicRouterTokenResult]:
    service = RouterProvisioningService(db)
    result = await service.get_public_token(tenant_id=ctx.tenant_id, router_id=router_id)
    return ApiResponse(data=result)


@router.post("/{router_id}/provisioning/complete", response_model=ApiResponse[RouterRead])
async def complete_router_provisioning(
    router_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RouterRead]:
    service = RouterProvisioningService(db)
    router_obj = await service.complete_provisioning(
        tenant_id=ctx.tenant_id, actor_id=ctx.user.id, router_id=router_id
    )
    await db.commit()
    return ApiResponse(data=RouterRead.model_validate(router_obj))
