#!/usr/bin/env bash
# Base provisioning for the Network VPS (Ubuntu 22.04/24.04 LTS).
#
# Installs and hardens: UFW, Fail2ban, WireGuard, FreeRADIUS + Postgres,
# Caddy. Idempotent-ish (safe to re-run), but this is a one-time setup
# script, not a config-management tool — read it before running it on a
# real box, and run it as root (or via sudo) on a fresh VPS.
#
# Usage: sudo ./provision-vps.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root (sudo ./provision-vps.sh)" >&2
    exit 1
fi

echo "==> Updating base packages"
apt-get update
apt-get upgrade -y

echo "==> Installing UFW, Fail2ban, WireGuard, Postgres, Caddy prerequisites"
apt-get install -y ufw fail2ban wireguard postgresql freeradius freeradius-postgresql \
    curl debian-keyring debian-archive-keyring apt-transport-https

echo "==> Installing Caddy (official repo)"
if ! command -v caddy >/dev/null 2>&1; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update
    apt-get install -y caddy
fi

echo "==> UFW: default deny, allow only SSH, WireGuard, and HTTPS"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
ufw allow 51820/udp comment "WireGuard"
ufw allow 443/tcp comment "Caddy (Network Agent TLS)"
ufw allow 80/tcp comment "Caddy (ACME HTTP challenge)"
# 1812/udp and 1813/udp (RADIUS) are intentionally NOT opened here — the
# `default` site in infrastructure/freeradius binds only to the WireGuard
# interface address, so the WireGuard tunnel itself is the access control,
# not a firewall hole to the public interface. UFW's default-deny-incoming
# already covers any other interface.
ufw --force enable

echo "==> Fail2ban: sshd + Caddy auth jail"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cp "$REPO_ROOT/infrastructure/fail2ban/jail.local" /etc/fail2ban/jail.local
mkdir -p /etc/fail2ban/filter.d
cp "$REPO_ROOT/infrastructure/fail2ban/filter.d/caddy-auth.conf" /etc/fail2ban/filter.d/caddy-auth.conf
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "==> WireGuard server config"
if [[ ! -f /etc/wireguard/wg0.conf ]]; then
    echo "    No /etc/wireguard/wg0.conf yet — copy"
    echo "    $REPO_ROOT/infrastructure/wireguard/wg0.conf.example to /etc/wireguard/wg0.conf,"
    echo "    generate a real key pair with 'wg genkey', and fill it in before enabling."
else
    systemctl enable --now wg-quick@wg0
fi

echo "==> FreeRADIUS config"
echo "    Copy $REPO_ROOT/infrastructure/freeradius/raddb/* into /etc/freeradius/3.0/,"
echo "    rename clients.conf.example -> clients.conf with real per-router secrets,"
echo "    symlink sites-enabled/default -> ../sites-available/default,"
echo "    set RADIUS_DB_* and RADIUS_LISTEN_ADDR in /etc/freeradius/3.0/radius_db.env"
echo "    (referenced by mods-available/sql and sites-available/default via \${env:...}),"
echo "    add it to the freeradius systemd unit's EnvironmentFile=, then:"
echo "    psql \"\$RADIUS_DATABASE_URL\" -f $REPO_ROOT/infrastructure/freeradius/schema/0001_radius_schema.sql"
echo "    systemctl enable --now freeradius"

echo "==> Caddy config"
cp "$REPO_ROOT/infrastructure/caddy/Caddyfile" /etc/caddy/Caddyfile
echo "    Edit /etc/caddy/Caddyfile to set the real domain, then:"
echo "    systemctl reload caddy"

echo "==> Network Agent systemd unit"
cp "$REPO_ROOT/infrastructure/systemd/network-agent.service" /etc/systemd/system/infinity-radius-network-agent.service
systemctl daemon-reload
echo "    Deploy the agent (see deploy-network-agent.sh) before enabling this unit."

echo "==> Done. Remaining manual steps are printed above — none of them"
echo "    involve committing a real secret to this repo."
