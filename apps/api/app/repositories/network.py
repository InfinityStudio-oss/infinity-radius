import ipaddress

from sqlalchemy import select

from app.models.network import Location, Router
from app.repositories.base import BaseRepository


class LocationRepository(BaseRepository[Location]):
    model = Location
    search_fields = ("name", "region", "city", "address")
    filterable_fields = ("status", "region", "city")
    sortable_fields = ("created_at", "name", "status")


class RouterRepository(BaseRepository[Router]):
    model = Router
    search_fields = ("name", "serial_number", "management_ip", "mac_address")
    filterable_fields = ("status", "location_id")
    sortable_fields = ("created_at", "name", "status", "last_seen_at")

    async def next_wireguard_tunnel_ip(self, *, subnet: str) -> str:
        """Picks the next free host address in `subnet` across every
        tenant's routers — the WireGuard tunnel is one shared address space
        on the Network VPS, not scoped per tenant. `.1` is reserved for the
        VPS itself (see infrastructure/wireguard/wg0.conf.example), so
        allocation starts at `.2`, matching
        infrastructure/scripts/add-router-peer.sh's own convention.

        This table is the source of truth for IPs the wizard assigns; a
        router provisioned instead via add-router-peer.sh's manual CLI flow
        must have its chosen IP recorded here too (e.g. via the wizard's
        network-config step) to avoid a double-assignment.
        """
        network = ipaddress.ip_network(subnet, strict=False)
        result = await self.db.execute(
            select(Router.wireguard_tunnel_ip).where(Router.wireguard_tunnel_ip.is_not(None))
        )
        assigned = {ipaddress.ip_address(ip) for ip in result.scalars().all() if ip}

        hosts = network.hosts()
        next(hosts, None)  # skip the first usable host (.1) — reserved for the VPS
        for host in hosts:
            if host not in assigned:
                return str(host)
        raise ValueError(f"No free addresses left in {subnet}")
