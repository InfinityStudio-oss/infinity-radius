#!/usr/bin/env bash
# Provisions a new MikroTik router as a WireGuard peer on the Network VPS.
#
# Generates a fresh key pair for the ROUTER side, picks the next free
# tunnel IP in the 10.90.0.0/24 range (matching wg0.conf.example's server
# address), appends a [Peer] block to the live /etc/wireguard/wg0.conf,
# and reloads the interface — then prints exactly what to paste into the
# router's own WireGuard setup (see router-peer.conf.example) and into
# infrastructure/freeradius/raddb/clients.conf for this router's RADIUS
# client secret.
#
# Nothing generated here is written back into this git repository — every
# key and IP assignment lives only in /etc/wireguard/wg0.conf on the VPS.
#
# Usage: sudo ./add-router-peer.sh <router-shortname>
# Example: sudo ./add-router-peer.sh kariakoo-site-1

set -euo pipefail

WG_CONF="/etc/wireguard/wg0.conf"
WG_SUBNET_PREFIX="10.90.0"
WG_INTERFACE="wg0"

if [[ $EUID -ne 0 ]]; then
    echo "Run as root (sudo ./add-router-peer.sh <router-shortname>)" >&2
    exit 1
fi

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <router-shortname>" >&2
    exit 1
fi
ROUTER_NAME="$1"

if [[ ! -f "$WG_CONF" ]]; then
    echo "$WG_CONF not found — provision the server interface first (see wg0.conf.example)." >&2
    exit 1
fi

# Next free host octet: highest currently-assigned AllowedIPs octet + 1,
# starting from .2 (.1 is the server itself).
last_octet=$(grep -oE "${WG_SUBNET_PREFIX}\.[0-9]+/32" "$WG_CONF" \
    | sed -E "s#${WG_SUBNET_PREFIX}\.([0-9]+)/32#\1#" \
    | sort -n | tail -1 || true)
next_octet=$(( ${last_octet:-1} + 1 ))
if (( next_octet > 254 )); then
    echo "No free addresses left in ${WG_SUBNET_PREFIX}.0/24" >&2
    exit 1
fi
ROUTER_IP="${WG_SUBNET_PREFIX}.${next_octet}"

umask 077
ROUTER_PRIVATE_KEY=$(wg genkey)
ROUTER_PUBLIC_KEY=$(echo "$ROUTER_PRIVATE_KEY" | wg pubkey)
SERVER_PUBLIC_KEY=$(grep -A5 '^\[Interface\]' "$WG_CONF" | grep '^PrivateKey' | awk '{print $3}' | wg pubkey)
RADIUS_SECRET=$(openssl rand -base64 24)

{
    echo ""
    echo "[Peer]"
    echo "# $ROUTER_NAME"
    echo "PublicKey = $ROUTER_PUBLIC_KEY"
    echo "AllowedIPs = ${ROUTER_IP}/32"
} >> "$WG_CONF"

wg syncconf "$WG_INTERFACE" <(wg-quick strip "$WG_INTERFACE")

cat <<EOF

==> Router "$ROUTER_NAME" provisioned as WireGuard peer $ROUTER_IP

--- Paste into the router (see infrastructure/wireguard/router-peer.conf.example) ---
/interface/wireguard add name=wg-radius listen-port=51820 private-key="$ROUTER_PRIVATE_KEY"
/interface/wireguard/peers add interface=wg-radius \\
    public-key="$SERVER_PUBLIC_KEY" \\
    endpoint-address=<network-vps-public-ip> endpoint-port=51820 \\
    allowed-address=${WG_SUBNET_PREFIX}.0/24 persistent-keepalive=25s
/ip/address add address=${ROUTER_IP}/32 interface=wg-radius
/radius add service=hotspot address=${WG_SUBNET_PREFIX}.1 secret="$RADIUS_SECRET" \\
    authentication-port=1812 accounting-port=1813
/ip/hotspot/profile set [find] use-radius=yes

--- Add to infrastructure/freeradius/raddb/clients.conf on the VPS ---
client $ROUTER_NAME {
    ipaddr     = $ROUTER_IP
    secret     = $RADIUS_SECRET
    shortname  = $ROUTER_NAME
    nas_type   = other
    require_message_authenticator = yes
}
then: systemctl reload freeradius

--- Record in the app ---
Add a row to infrastructure/freeradius's "nas" table (nasname=$ROUTER_IP,
shortname=$ROUTER_NAME, secret=$RADIUS_SECRET) if using SQL-loaded clients
instead of the static clients.conf above, and add this router's connection
details (router_id UUID, host=$ROUTER_IP) to the Network Agent's
routers.yaml registry (see apps/network-agent/routers.yaml.example) — the
Network Agent never accepts an IP from the caller, only a router UUID it
resolves itself.
EOF
