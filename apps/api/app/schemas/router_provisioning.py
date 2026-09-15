"""Add Router Wizard request/response shapes. Every "generate" response
carries a plaintext secret exactly once (the moment it's created) — never
again afterwards; re-fetching a router never returns it (see
app/schemas/network.py's RouterRead, which has no secret fields at all)."""

from pydantic import BaseModel, Field, IPvAnyAddress, IPvAnyNetwork


class NetworkConfigRequest(BaseModel):
    network_cidr: IPvAnyNetwork
    gateway_ip: IPvAnyAddress
    dns_servers: list[IPvAnyAddress] = Field(min_length=1, max_length=4)


class NetworkConfigRead(BaseModel):
    network_cidr: str
    gateway_ip: str
    dns_servers: list[str]


class WireGuardConfigResult(BaseModel):
    tunnel_ip: str
    router_private_key: str  # shown once — never stored in plaintext, never re-returned
    router_public_key: str
    server_public_key: str
    server_endpoint: str
    allowed_ips: str
    router_config_script: str  # paste into RouterOS terminal
    server_peer_block: str  # append to the VPS's wg0.conf


class RadiusConfigResult(BaseModel):
    secret: str  # shown once
    router_config_script: str
    nas_client_block: str  # for infrastructure/freeradius/raddb/clients.conf


class HotspotConfigResult(BaseModel):
    router_config_script: str


class WalledGardenResult(BaseModel):
    domains: list[str]
    router_config_script: str


class PublicRouterTokenResult(BaseModel):
    router_token: str
    example_redirect_url: str
