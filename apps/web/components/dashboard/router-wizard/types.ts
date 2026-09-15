/** Mirrors apps/api/app/schemas/router_provisioning.py, network.py, and
 * integrations/network_agent/schemas.py — keep these in sync by hand. */

export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
}

export interface Location {
  id: string;
  name: string;
  region: string | null;
  city: string | null;
}

export interface RouterRead {
  id: string;
  tenant_id: string;
  location_id: string | null;
  name: string;
  serial_number: string | null;
  model: string | null;
  management_ip: string | null;
  mac_address: string | null;
  firmware_version: string | null;
  status: string;
  provisioning_status: "in_progress" | "completed";
  hotspot_network_cidr: string | null;
  hotspot_gateway_ip: string | null;
  hotspot_dns_servers: string | null;
  wireguard_public_key: string | null;
  wireguard_tunnel_ip: string | null;
}

export interface NetworkConfigRead {
  network_cidr: string;
  gateway_ip: string;
  dns_servers: string[];
}

export interface WireGuardConfigResult {
  tunnel_ip: string;
  router_private_key: string;
  router_public_key: string;
  server_public_key: string;
  server_endpoint: string;
  allowed_ips: string;
  router_config_script: string;
  server_peer_block: string;
}

export interface RadiusConfigResult {
  secret: string;
  router_config_script: string;
  nas_client_block: string;
}

export interface HotspotConfigResult {
  router_config_script: string;
}

export interface WalledGardenResult {
  domains: string[];
  router_config_script: string;
}

export interface PublicRouterTokenResult {
  router_token: string;
  example_redirect_url: string;
}

export interface TestConnectionResult {
  reachable: boolean;
  latency_ms: number | null;
  detail: string | null;
}
