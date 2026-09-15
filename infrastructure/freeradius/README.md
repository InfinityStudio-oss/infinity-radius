# FreeRADIUS

Runs on the Network VPS (not Railway), backed by its own PostgreSQL instance
(separate from the Supabase primary database). MikroTik routers authenticate
and account hotspot sessions against this FreeRADIUS instance over the
WireGuard tunnel — 1812/UDP for authentication, 1813/UDP for accounting.

## Layout

```
infrastructure/freeradius/
  schema/
    0001_radius_schema.sql   # radcheck, radreply, radusergroup, radgroupcheck,
                              # radgroupreply, radacct, radpostauth, nas
    mikrotik_attributes.md   # how a package becomes a RADIUS group's attributes
  raddb/
    dictionary                # includes the stock + MikroTik vendor dictionaries
    clients.conf.example       # NAS (router) client template — no real secrets
    mods-available/sql         # SQL module config (env-var connection, stock queries)
    sites-available/default    # auth (1812) + acct (1813) virtual server
  docker-compose.yml          # local dev: freeradius + postgres for RADIUS
  .env.example
```

## Design choices

- **Schema matches FreeRADIUS's own postgresql schema column-for-column** —
  `rlm_sql`'s stock `queries.conf` (which this config `$INCLUDE`s rather
  than reimplementing) references these column names directly. `nas` gets
  two additive columns, `tenant_id`/`router_id`, purely for Infinity
  Radius's own reporting joins; FreeRADIUS never reads them.
- **One RADIUS group per package** (`pkg_<package-uuid>`) — see
  `schema/mikrotik_attributes.md` for exactly how `Mikrotik-Rate-Limit`,
  `Session-Timeout`, and `Simultaneous-Use` map from a `packages` row.
- **PAP only, no EAP** — MikroTik hotspot authenticates customers via the
  walled-garden login page (username/password), not 802.1X, so
  `sites-available/default` has no inner-tunnel/EAP config.
- **Binds only to the WireGuard interface** — never `0.0.0.0` in
  production (`RADIUS_LISTEN_ADDR` in `.env`/`radius_db.env` on the VPS).
  The local `docker-compose.yml` overrides this to `0.0.0.0` only because
  there's no WireGuard interface inside a container — documented inline.
- **No secrets committed** — `clients.conf.example` and `.env.example`
  contain placeholders only; real per-router RADIUS secrets and the
  database password are set operationally on the VPS (or in a local
  untracked `.env` for `docker-compose.yml`).

## Local dev

```bash
cd infrastructure/freeradius
cp .env.example .env   # fill in a local-only RADIUS_DB_PASSWORD
docker compose up
```

## Production

Installed by `infrastructure/scripts/provision-vps.sh` alongside WireGuard,
Caddy, UFW, and Fail2ban. `raddb/` is copied to `/etc/freeradius/3.0/`
(symlinking `sites-enabled/default` -> `sites-available/default`), and
`schema/0001_radius_schema.sql` is applied once against the VPS's own
RADIUS Postgres instance — see `infrastructure/scripts/README.md`.

## Environment

The API and worker connect to this database via `RADIUS_DATABASE_URL`
(see `apps/api/.env.example`), kept separate from `DATABASE_URL` (Supabase)
because RADIUS accounting write volume and access patterns are very
different from the primary application database.
