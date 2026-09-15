-- Infinity Radius — RADIUS PostgreSQL schema.
--
-- Adapted from FreeRADIUS's own postgresql schema
-- (mods-config/sql/main/postgresql/schema.sql, FreeRADIUS 3.2.x) — column
-- names and types are kept identical to the upstream schema because
-- rlm_sql's default queries.conf references them by name. Do not rename
-- radcheck/radreply/radusergroup/radgroupcheck/radgroupreply/radacct/
-- radpostauth/nas columns; the queries in raddb/mods-available/sql depend
-- on the stock names.
--
-- Two additive, non-standard columns are appended to `nas` only
-- (tenant_id, router_id) so Infinity Radius can join a RADIUS client back
-- to the tenant/router that owns it for reporting. FreeRADIUS itself never
-- reads or writes them — they are ignored by every stock query.
--
-- This database is entirely separate from the primary Supabase Postgres
-- database (see RADIUS_DATABASE_URL) — different write volume/access
-- pattern (radacct is accounting-write-heavy), and FreeRADIUS owns it
-- directly rather than going through the API's SQLAlchemy models.
--
-- Run this against a fresh RADIUS database:
--   psql "$RADIUS_DATABASE_URL" -f 0001_radius_schema.sql

-- =============================================================================
-- radcheck — per-user check attributes (e.g. Cleartext-Password, Simultaneous-Use)
-- =============================================================================
CREATE TABLE IF NOT EXISTS radcheck (
    id        SERIAL PRIMARY KEY,
    username  TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op        VARCHAR(2) NOT NULL DEFAULT '==',
    value     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS radcheck_username ON radcheck (username, attribute);

-- =============================================================================
-- radreply — per-user reply attributes (e.g. Mikrotik-Rate-Limit override)
-- =============================================================================
CREATE TABLE IF NOT EXISTS radreply (
    id        SERIAL PRIMARY KEY,
    username  TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op        VARCHAR(2) NOT NULL DEFAULT '=',
    value     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS radreply_username ON radreply (username, attribute);

-- =============================================================================
-- radusergroup — maps a RADIUS username to one or more groups (packages)
-- =============================================================================
CREATE TABLE IF NOT EXISTS radusergroup (
    id        SERIAL PRIMARY KEY,
    username  TEXT NOT NULL DEFAULT '',
    groupname TEXT NOT NULL DEFAULT '',
    priority  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS radusergroup_username ON radusergroup (username);

-- =============================================================================
-- radgroupcheck — per-group check attributes (e.g. Simultaneous-Use)
-- One group per Infinity Radius package (see mikrotik_attributes.md).
-- =============================================================================
CREATE TABLE IF NOT EXISTS radgroupcheck (
    id        SERIAL PRIMARY KEY,
    groupname TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op        VARCHAR(2) NOT NULL DEFAULT '==',
    value     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS radgroupcheck_groupname ON radgroupcheck (groupname, attribute);

-- =============================================================================
-- radgroupreply — per-group reply attributes: this is where a package's
-- Mikrotik-Rate-Limit / Session-Timeout / Idle-Timeout live.
-- =============================================================================
CREATE TABLE IF NOT EXISTS radgroupreply (
    id        SERIAL PRIMARY KEY,
    groupname TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op        VARCHAR(2) NOT NULL DEFAULT '=',
    value     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS radgroupreply_groupname ON radgroupreply (groupname, attribute);

-- =============================================================================
-- radacct — accounting: one row per hotspot session, updated as it runs.
-- =============================================================================
CREATE TABLE IF NOT EXISTS radacct (
    radacctid           BIGSERIAL PRIMARY KEY,
    acctsessionid       TEXT NOT NULL,
    acctuniqueid        TEXT NOT NULL UNIQUE,
    username            TEXT,
    groupname           TEXT,
    realm               TEXT,
    nasipaddress        INET NOT NULL,
    nasportid           TEXT,
    nasporttype         TEXT,
    acctstarttime       TIMESTAMP WITH TIME ZONE,
    acctupdatetime      TIMESTAMP WITH TIME ZONE,
    acctstoptime        TIMESTAMP WITH TIME ZONE,
    acctinterval        BIGINT,
    acctsessiontime     BIGINT,
    acctauthentic       TEXT,
    connectinfo_start   TEXT,
    connectinfo_stop    TEXT,
    acctinputoctets     BIGINT,
    acctoutputoctets    BIGINT,
    calledstationid     TEXT,
    callingstationid    TEXT,
    acctterminatecause  TEXT,
    servicetype         TEXT,
    framedprotocol      TEXT,
    framedipaddress     INET,
    framedipv6address   INET,
    framedipv6prefix    INET,
    framedinterfaceid   TEXT,
    delegatedipv6prefix INET
);
CREATE INDEX IF NOT EXISTS radacct_active_user_idx
    ON radacct (username, nasipaddress, acctstarttime) WHERE acctstoptime IS NULL;
CREATE INDEX IF NOT EXISTS radacct_bulk_close
    ON radacct (nasipaddress, acctstarttime) WHERE acctstoptime IS NULL;
CREATE INDEX IF NOT EXISTS radacct_start_user_idx ON radacct (acctstarttime, username);
CREATE INDEX IF NOT EXISTS radacct_stop_time_idx ON radacct (acctstoptime);

-- =============================================================================
-- radpostauth — one row per auth attempt (accept or reject), for audit trail.
-- =============================================================================
CREATE TABLE IF NOT EXISTS radpostauth (
    id       BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    pass     TEXT,
    reply    TEXT,
    authdate TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    class    TEXT
);

-- =============================================================================
-- nas — the RADIUS clients (MikroTik routers) allowed to talk to this
-- FreeRADIUS instance. `secret` is the RADIUS shared secret configured on
-- the router — NEVER a real value in this repo; every row is inserted
-- operationally, never via a checked-in migration/seed.
--
-- tenant_id / router_id are additive — FreeRADIUS's own queries never
-- reference them; they exist purely so Infinity Radius can join a `nas`
-- row back to `public.tenants` / `public.routers` in the primary database
-- for reporting (there is no cross-database FK — these are plain UUID
-- columns, validated at the application layer).
-- =============================================================================
CREATE TABLE IF NOT EXISTS nas (
    id          SERIAL PRIMARY KEY,
    nasname     TEXT NOT NULL,
    shortname   TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'mikrotik',
    ports       INTEGER,
    secret      TEXT NOT NULL,
    server      TEXT,
    community   TEXT,
    description TEXT,
    tenant_id   UUID,
    router_id   UUID
);
CREATE INDEX IF NOT EXISTS nas_tenant_id_idx ON nas (tenant_id);
CREATE INDEX IF NOT EXISTS nas_router_id_idx ON nas (router_id);

-- No rows are inserted by this migration. `nas` (router clients),
-- `radgroupcheck`/`radgroupreply` (package -> RADIUS attribute mapping),
-- and `radcheck`/`radusergroup` (customer credentials) are populated only
-- by real tenant/router/package/customer data flowing through the API —
-- never a seeded/sample value.
