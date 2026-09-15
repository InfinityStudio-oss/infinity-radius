"""Backs the Add Router Wizard's generation steps (network config,
WireGuard, RADIUS, hotspot, walled garden, public token). Every "generate"
method persists what it creates against the router row immediately —
there's no separate draft/commit step; `complete_provisioning` (wizard
step 9, "Save router") just marks the router ready for use.

Secrets (RADIUS secret, WireGuard private key) are encrypted at rest
(app.core.crypto) and returned in plaintext exactly once, in the response
of the call that generates them — never persisted in plaintext, never
re-returned by a later read.
"""

import base64
import ipaddress
import secrets
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import encrypt_secret
from app.core.errors import DomainValidationError, NotFoundError
from app.core.router_token import create_router_token
from app.models.network import Router
from app.repositories.network import RouterRepository
from app.schemas.router_provisioning import (
    HotspotConfigResult,
    NetworkConfigRead,
    PublicRouterTokenResult,
    RadiusConfigResult,
    WalledGardenResult,
    WireGuardConfigResult,
)
from app.services.audit import write_audit_log

_RADIUS_AUTH_PORT = 1812
_RADIUS_ACCT_PORT = 1813


def _generate_wireguard_keypair() -> tuple[str, str]:
    """Returns (private_key, public_key) as WireGuard expects them: 32 raw
    Curve25519 bytes, standard (not urlsafe) base64 — the same encoding
    `wg genkey`/`wg pubkey` produce."""
    private_key = X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(private_bytes).decode("ascii"), base64.b64encode(
        public_bytes
    ).decode("ascii")


class RouterProvisioningService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = RouterRepository(db)

    async def _get_router(self, *, tenant_id: UUID, router_id: UUID) -> Router:
        router = await self.repo.get_by_id(tenant_id=tenant_id, id=router_id)
        if router is None:
            raise NotFoundError("Router not found")
        return router

    async def set_network_config(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        router_id: UUID,
        network_cidr: str,
        gateway_ip: str,
        dns_servers: list[str],
    ) -> NetworkConfigRead:
        router = await self._get_router(tenant_id=tenant_id, router_id=router_id)
        network = ipaddress.ip_network(network_cidr, strict=False)
        gateway = ipaddress.ip_address(gateway_ip)
        if gateway not in network:
            raise DomainValidationError(
                f"gateway_ip {gateway_ip} is not inside network_cidr {network_cidr}"
            )

        await self.repo.update(
            router,
            hotspot_network_cidr=str(network),
            hotspot_gateway_ip=str(gateway),
            hotspot_dns_servers=",".join(dns_servers),
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="router.network_config_set",
            target_type="router",
            target_id=router.id,
        )
        return NetworkConfigRead(
            network_cidr=str(network), gateway_ip=str(gateway), dns_servers=dns_servers
        )

    async def generate_wireguard_config(
        self, *, tenant_id: UUID, actor_id: UUID, router_id: UUID
    ) -> WireGuardConfigResult:
        settings = get_settings()
        if not settings.wireguard_server_public_key or not settings.wireguard_server_endpoint:
            raise DomainValidationError(
                "WIREGUARD_SERVER_PUBLIC_KEY / WIREGUARD_SERVER_ENDPOINT are not configured "
                "— set them to the Network VPS's real wg0.conf values first."
            )

        router = await self._get_router(tenant_id=tenant_id, router_id=router_id)
        tunnel_ip = await self.repo.next_wireguard_tunnel_ip(
            subnet=settings.wireguard_server_subnet
        )
        private_key, public_key = _generate_wireguard_keypair()

        await self.repo.update(
            router,
            wireguard_public_key=public_key,
            wireguard_tunnel_ip=tunnel_ip,
            wireguard_private_key_encrypted=encrypt_secret(private_key),
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="router.wireguard_config_generated",
            target_type="router",
            target_id=router.id,
            metadata={"tunnel_ip": tunnel_ip},
        )

        allowed_ips = settings.wireguard_server_subnet
        router_config_script = (
            f"/interface/wireguard add name=wg-radius listen-port=51820 "
            f'private-key="{private_key}"\n'
            f"/interface/wireguard/peers add interface=wg-radius \\\n"
            f'    public-key="{settings.wireguard_server_public_key}" \\\n'
            f"    endpoint-address={settings.wireguard_server_endpoint.split(':')[0]} "
            f"endpoint-port={settings.wireguard_server_endpoint.split(':')[-1]} \\\n"
            f"    allowed-address={allowed_ips} persistent-keepalive=25s\n"
            f"/ip/address add address={tunnel_ip}/32 interface=wg-radius"
        )
        server_peer_block = (
            f"[Peer]\n# {router.name}\nPublicKey = {public_key}\nAllowedIPs = {tunnel_ip}/32"
        )

        return WireGuardConfigResult(
            tunnel_ip=tunnel_ip,
            router_private_key=private_key,
            router_public_key=public_key,
            server_public_key=settings.wireguard_server_public_key,
            server_endpoint=settings.wireguard_server_endpoint,
            allowed_ips=allowed_ips,
            router_config_script=router_config_script,
            server_peer_block=server_peer_block,
        )

    async def generate_radius_config(
        self, *, tenant_id: UUID, actor_id: UUID, router_id: UUID
    ) -> RadiusConfigResult:
        router = await self._get_router(tenant_id=tenant_id, router_id=router_id)
        if not router.wireguard_tunnel_ip:
            raise DomainValidationError(
                "Generate the WireGuard configuration first — the RADIUS server address "
                "is this router's own tunnel IP's gateway, and the NAS client entry needs "
                "this router's tunnel IP."
            )

        settings = get_settings()
        radius_server_ip = str(
            next(ipaddress.ip_network(settings.wireguard_server_subnet, strict=False).hosts())
        )
        secret = secrets.token_urlsafe(24)

        await self.repo.update(router, radius_secret_encrypted=encrypt_secret(secret))
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="router.radius_config_generated",
            target_type="router",
            target_id=router.id,
        )

        router_config_script = (
            f"/radius add service=hotspot address={radius_server_ip} "
            f'secret="{secret}" authentication-port={_RADIUS_AUTH_PORT} '
            f"accounting-port={_RADIUS_ACCT_PORT}\n"
            f"/ip/hotspot/profile set [find] use-radius=yes"
        )
        nas_client_block = (
            f"client {router.name} {{\n"
            f"    ipaddr     = {router.wireguard_tunnel_ip}\n"
            f'    secret     = {secret}\n'
            f"    shortname  = {router.name}\n"
            f"    nas_type   = mikrotik\n"
            f"    require_message_authenticator = yes\n"
            f"}}"
        )
        return RadiusConfigResult(
            secret=secret,
            router_config_script=router_config_script,
            nas_client_block=nas_client_block,
        )

    async def generate_hotspot_config(
        self, *, tenant_id: UUID, actor_id: UUID, router_id: UUID
    ) -> HotspotConfigResult:
        router = await self._get_router(tenant_id=tenant_id, router_id=router_id)
        if not router.hotspot_network_cidr or not router.hotspot_gateway_ip:
            raise DomainValidationError("Set the network configuration first (wizard step 3).")

        network = ipaddress.ip_network(router.hotspot_network_cidr, strict=False)
        hosts = list(network.hosts())
        pool_start = hosts[1] if len(hosts) > 1 else hosts[0]
        pool_end = hosts[-1]
        dns_servers = router.hotspot_dns_servers or ""

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="router.hotspot_config_generated",
            target_type="router",
            target_id=router.id,
        )

        router_config_script = (
            f"/ip/pool add name=hotspot-pool ranges={pool_start}-{pool_end}\n"
            f"/ip/address add address={router.hotspot_gateway_ip}/"
            f"{network.prefixlen} interface=bridge-hotspot\n"
            f"/ip/dhcp-server/network add address={network} "
            f"gateway={router.hotspot_gateway_ip} dns-server={dns_servers}\n"
            f"/ip/hotspot/profile add name=infinity-radius hotspot-address="
            f"{router.hotspot_gateway_ip} dns-name=hotspot.local use-radius=yes\n"
            f"/ip/hotspot add name=infinity-radius interface=bridge-hotspot "
            f"address-pool=hotspot-pool profile=infinity-radius"
        )
        return HotspotConfigResult(router_config_script=router_config_script)

    async def generate_walled_garden_rules(
        self, *, tenant_id: UUID, actor_id: UUID, router_id: UUID
    ) -> WalledGardenResult:
        router = await self._get_router(tenant_id=tenant_id, router_id=router_id)
        settings = get_settings()

        domains = [
            domain
            for domain in (settings.public_captive_portal_domain, settings.public_api_domain)
            if domain
        ]
        if not domains:
            raise DomainValidationError(
                "PUBLIC_CAPTIVE_PORTAL_DOMAIN / PUBLIC_API_DOMAIN are not configured — "
                "the walled garden needs at least one real domain, never a wildcard fallback."
            )

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="router.walled_garden_generated",
            target_type="router",
            target_id=router.id,
            metadata={"domains": domains},
        )

        lines = [
            f"/ip/hotspot/walled-garden add dst-host={domain} action=allow"
            for domain in domains
        ]
        return WalledGardenResult(domains=domains, router_config_script="\n".join(lines))

    async def get_public_token(
        self, *, tenant_id: UUID, router_id: UUID
    ) -> PublicRouterTokenResult:
        router = await self._get_router(tenant_id=tenant_id, router_id=router_id)
        settings = get_settings()
        token = create_router_token(router.id)

        portal_domain = settings.public_captive_portal_domain or "<captive-portal-domain>"
        # $(link-login-only) is the router's own local login endpoint —
        # not sensitive (same LAN the client is already on), and required
        # so the portal (a different origin) can submit the final hotspot
        # login form once payment completes. See app/api/v1/public.py's
        # resolve endpoint and docs/architecture.md's Captive portal section.
        example_url = (
            f"https://{portal_domain}/captive-portal"
            f"?router={token}&mac=$(mac)&dst=$(link-orig)&login=$(link-login-only)"
        )
        return PublicRouterTokenResult(router_token=token, example_redirect_url=example_url)

    async def complete_provisioning(
        self, *, tenant_id: UUID, actor_id: UUID, router_id: UUID
    ) -> Router:
        router = await self._get_router(tenant_id=tenant_id, router_id=router_id)
        router = await self.repo.update(router, provisioning_status="completed")
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="router.provisioning_completed",
            target_type="router",
            target_id=router.id,
        )
        return router
