# Package -> RADIUS attribute mapping

How an Infinity Radius `packages` row (see `apps/api/app/models/network.py`)
becomes RADIUS reply attributes a MikroTik hotspot enforces. Nothing in this
file is executed automatically — it documents the mapping and gives
illustrative SQL a tenant's package sync job would issue against
`radgroupcheck`/`radgroupreply`, not a seed script.

## Attribute reference

| Attribute            | Standard          | Meaning                                                        |
| --------------------- | ------------------ | --------------------------------------------------------------- |
| `Mikrotik-Rate-Limit` | MikroTik VSA (vendor 14988) | Bandwidth shape: `"rx-rate/tx-rate"`, e.g. `"2M/2M"`. Ships in FreeRADIUS's own `dictionary.mikrotik` — see `raddb/dictionary`. |
| `Session-Timeout`     | RFC 2865, attribute 27 | Max session length in seconds before RADIUS-initiated disconnect. Maps from `packages.duration_minutes * 60`. |
| `Idle-Timeout`        | RFC 2865, attribute 28 | Max idle time in seconds before disconnect. Set per package/tenant policy — not stored on `packages` today. |
| `Simultaneous-Use`    | FreeRADIUS check-item (not a wire attribute) | Enforced via `radcheck`/`radgroupcheck` + the SQL module's `simul_use_query`/`simul_count_query` (see `raddb/mods-available/sql`). Maps from `packages.simultaneous_sessions`. |

`Mikrotik-Rate-Limit` is a reply (`radgroupreply`) attribute; `Session-Timeout`
and `Idle-Timeout` are also reply attributes; `Simultaneous-Use` is a check
(`radgroupcheck`) attribute — it constrains the auth decision, it isn't sent
back to the router.

## One RADIUS group per package

Each package becomes one `radgroupcheck`/`radgroupreply` group, named
`pkg_<package_id>` (the package's UUID) so the mapping is unambiguous and
collision-free across tenants without needing a `tenant_id` column on these
FreeRADIUS-owned tables.

```sql
-- Illustrative only — real values come from a real packages row via the
-- (future) package -> RADIUS sync job, never typed in by hand.
INSERT INTO radgroupreply (groupname, attribute, op, value) VALUES
    ('pkg_<package-uuid>', 'Mikrotik-Rate-Limit', ':=', '<download>k/<upload>k'),
    ('pkg_<package-uuid>', 'Session-Timeout',     ':=', '<duration_minutes * 60>');

INSERT INTO radgroupcheck (groupname, attribute, op, value) VALUES
    ('pkg_<package-uuid>', 'Simultaneous-Use', ':=', '<simultaneous_sessions>');
```

A customer's `radusergroup` row then assigns them to that package's group:

```sql
INSERT INTO radusergroup (username, groupname, priority)
VALUES ('<customer phone, 2557XXXXXXXX>', 'pkg_<package-uuid>', 1);
```

`bytes_limit` (a package's data cap) is not a standard RADIUS reply attribute
FreeRADIUS enforces on its own — MikroTik hotspot enforces data caps via
`radacct`-based accounting checked by the Network Agent/worker (a session
transitioning a subscription to `QUOTA_EXCEEDED` — see
`apps/api/app/core/enums.py`), not via a RADIUS attribute sent at auth time.
