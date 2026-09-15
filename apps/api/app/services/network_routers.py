from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import ListParams
from app.integrations.network_agent.client import (
    NetworkAgentClient,
    NetworkAgentError,
    NetworkAgentNotConfiguredError,
)
from app.integrations.network_agent.schemas import TestConnectionResult
from app.models.network import Router
from app.repositories.network import RouterRepository
from app.schemas.network import RouterHealthRead
from app.services.audit import write_audit_log


class RouterService:
    """MikroTik routers. `status`/`last_seen_at` are only ever updated by the
    Network Agent integration once it exists — never fabricated here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = RouterRepository(db)

    async def health(self, *, tenant_id: UUID) -> list[RouterHealthRead]:
        """Every router this tenant owns, with whatever health signal is
        actually real today: `status`/`last_seen_at` from the row itself
        (honest even when that means "unknown"/null — see this class's
        docstring), and `None` for active_users/latency_ms/cpu_load_pct/
        uptime_seconds because no telemetry pipeline exists to report them
        yet. Never a random or guessed number for those four fields.

        Defined before `list()` below on purpose: a method literally named
        `list` shadows the builtin for the rest of this class body, which
        breaks any later method's bare `list[...]` return annotation."""
        routers, _total = await self.repo.list_paginated(
            tenant_id=tenant_id,
            params=ListParams(page=1, page_size=1000, search=None, sort="name"),
        )
        return [
            RouterHealthRead(
                id=router.id,
                name=router.name,
                status=router.status,
                last_seen_at=router.last_seen_at,
                active_users=None,
                latency_ms=None,
                cpu_load_pct=None,
                uptime_seconds=None,
            )
            for router in routers
        ]

    async def list(self, *, tenant_id: UUID, params: ListParams) -> tuple[list[Router], int]:
        return await self.repo.list_paginated(tenant_id=tenant_id, params=params)

    async def get(self, *, tenant_id: UUID, router_id: UUID) -> Router:
        router = await self.repo.get_by_id(tenant_id=tenant_id, id=router_id)
        if router is None:
            raise NotFoundError("Router not found")
        return router

    async def create(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        name: str,
        location_id: UUID | None,
        model: str | None,
        management_ip: str | None,
        mac_address: str | None,
    ) -> Router:
        router = await self.repo.create(
            tenant_id=tenant_id,
            name=name,
            location_id=location_id,
            model=model,
            management_ip=management_ip,
            mac_address=mac_address,
            status="unknown",
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="router.created",
            target_type="router",
            target_id=router.id,
        )
        return router

    async def test_connection(self, *, tenant_id: UUID, router_id: UUID) -> TestConnectionResult:
        """Router -> Railway (this call) -> HTTPS -> Network Agent ->
        WireGuard -> MikroTik. Only this router's own UUID is ever sent —
        the Network Agent resolves it to real connection details itself."""
        router = await self.get(tenant_id=tenant_id, router_id=router_id)
        try:
            async with NetworkAgentClient() as client:
                return await client.test_connection(router_id=router.id)
        except NetworkAgentNotConfiguredError as exc:
            return TestConnectionResult(reachable=False, detail=str(exc))
        except NetworkAgentError as exc:
            return TestConnectionResult(reachable=False, detail=str(exc))
