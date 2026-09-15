# Infrastructure scripts

Operational scripts for the Network VPS.

- `provision-vps.sh` — base Ubuntu hardening + installs UFW, Fail2ban,
  WireGuard, FreeRADIUS + Postgres, and Caddy. Run once on a fresh VPS.
- `add-router-peer.sh <shortname>` — generates a WireGuard key pair for a
  new MikroTik router, assigns it the next free tunnel IP, appends it to
  the live `wg0.conf`, and prints the RouterOS commands + FreeRADIUS
  `clients.conf` block to configure that router.
- `deploy-network-agent.sh [git-ref]` — pulls the latest Network Agent code
  and restarts its systemd service.

Related files live in sibling directories and are copied into place by
`provision-vps.sh`:

- `infrastructure/fail2ban/jail.local` + `filter.d/caddy-auth.conf`
- `infrastructure/caddy/Caddyfile`
- `infrastructure/systemd/network-agent.service`

None of these scripts modify anything in this git repository — every key,
secret, and peer assignment they generate lives only on the VPS (or, for
FreeRADIUS client secrets, in the `nas` table / `clients.conf`).
