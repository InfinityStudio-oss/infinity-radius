"""One-time (but safely re-runnable) local development bootstrap for the
RADIUS Postgres database.

This is a SEPARATE database from the primary app database (DATABASE_URL,
real Supabase Postgres) — see infrastructure/freeradius/schema/
0001_radius_schema.sql for why. In production this schema lives on the
FreeRADIUS Network VPS; locally, it lives in its own database on the same
local Postgres instance already used for the primary app's test database.

What this script does, in order:
    1. Connects to the local Postgres instance as the superuser (same
       well-known local-dev credential already hardcoded in
       tests/conftest.py — not a new secret, and never a production one).
    2. Creates the `radius` database if it doesn't already exist.
    3. Creates a dedicated, least-privilege `radius_app` role if it
       doesn't already exist (generating a real random password) — the
       API never connects to this database as the Postgres superuser.
    4. Applies infrastructure/freeradius/schema/0001_radius_schema.sql
       (idempotent: every statement is CREATE TABLE IF NOT EXISTS /
       CREATE INDEX IF NOT EXISTS).
    5. Grants radius_app exactly the privileges app/services/radius_sync.py
       needs (SELECT/INSERT/UPDATE/DELETE on the RADIUS tables, USAGE on
       their sequences) — nothing more.
    6. Writes the resulting RADIUS_DATABASE_URL into apps/api/.env
       directly, so the real local password is never printed to the
       terminal or pasted into a report — only safe metadata (host, port,
       database name, role name) is ever printed.
    7. Verifies the connection *as radius_app* (not as the superuser) and
       confirms every expected table is reachable.

Safe to run multiple times: an existing database/role/schema/grant is
detected and left alone rather than recreated.

Usage:
    cd apps/api
    python -m scripts.setup_local_radius_db
"""

from __future__ import annotations

import re
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg import sql

ADMIN_DSN = "postgresql://postgres:postgres_local_dev@localhost:5432/postgres"
RADIUS_DB_NAME = "radius"
RADIUS_ROLE = "radius_app"
RADIUS_HOST = "localhost"
RADIUS_PORT = 5432

SCHEMA_FILE = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "freeradius"
    / "schema"
    / "0001_radius_schema.sql"
)
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

EXPECTED_TABLES = [
    "radcheck",
    "radreply",
    "radgroupcheck",
    "radgroupreply",
    "radusergroup",
    "radacct",
    "radpostauth",
    "nas",
]


def _database_exists(admin_conn: psycopg.Connection, name: str) -> bool:
    with admin_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        return cur.fetchone() is not None


def _role_exists(admin_conn: psycopg.Connection, name: str) -> bool:
    with admin_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,))
        return cur.fetchone() is not None


def _existing_radius_password_from_env() -> str | None:
    """If a prior run of this script already wrote a working
    RADIUS_DATABASE_URL for RADIUS_ROLE into .env, reuse that exact
    password instead of generating a new one the role doesn't actually
    have — this is what makes re-running the script safe once the role
    already exists."""
    if not ENV_FILE.exists():
        return None
    match = re.search(
        rf"^RADIUS_DATABASE_URL=postgresql\+asyncpg://{re.escape(RADIUS_ROLE)}:([^@]+)@",
        ENV_FILE.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    return match.group(1) if match else None


def _write_env(password: str) -> None:
    url_line = (
        f"RADIUS_DATABASE_URL=postgresql+asyncpg://{RADIUS_ROLE}:{quote(password)}"
        f"@{RADIUS_HOST}:{RADIUS_PORT}/{RADIUS_DB_NAME}\n"
    )
    if not ENV_FILE.exists():
        print(f"error: {ENV_FILE} does not exist -- copy .env.example first.", file=sys.stderr)
        raise SystemExit(1)

    text = ENV_FILE.read_text(encoding="utf-8")
    if re.search(r"^RADIUS_DATABASE_URL=.*$", text, flags=re.MULTILINE):
        text = re.sub(r"^RADIUS_DATABASE_URL=.*$", url_line.rstrip("\n"), text, flags=re.MULTILINE)
    else:
        text = text.rstrip("\n") + "\n" + url_line
    ENV_FILE.write_text(text, encoding="utf-8")


def main() -> None:
    try:
        admin_conn = psycopg.connect(ADMIN_DSN, autocommit=True)
    except psycopg.OperationalError as exc:
        print(
            f"Could not reach local Postgres at {RADIUS_HOST}:{RADIUS_PORT}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    with admin_conn:
        db_existed = _database_exists(admin_conn, RADIUS_DB_NAME)
        if not db_existed:
            with admin_conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{RADIUS_DB_NAME}"')
            print(f"Created database {RADIUS_DB_NAME!r}.")
        else:
            print(f"Database {RADIUS_DB_NAME!r} already exists -- leaving it alone.")

        role_existed = _role_exists(admin_conn, RADIUS_ROLE)
        if role_existed:
            password = _existing_radius_password_from_env()
            if password is None:
                print(
                    f"error: role {RADIUS_ROLE!r} already exists but its password isn't in "
                    f"{ENV_FILE} -- either restore the .env entry or drop the role "
                    f"(DROP ROLE {RADIUS_ROLE};) and re-run this script to recreate it.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            print(f"Role {RADIUS_ROLE!r} already exists -- reusing its existing local password.")
        else:
            password = secrets.token_urlsafe(24)
            with admin_conn.cursor() as cur:
                # DDL doesn't support bind parameters — psycopg.sql.Literal
                # safely escapes the password as a SQL string literal
                # instead of interpolating it directly.
                cur.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(RADIUS_ROLE), sql.Literal(password)
                    )
                )
            print(f"Created role {RADIUS_ROLE!r}.")

    # Schema + grants run against the `radius` database itself, still as
    # the superuser (the app role is granted privileges, not ownership).
    radius_admin_dsn = ADMIN_DSN.rsplit("/", 1)[0] + f"/{RADIUS_DB_NAME}"
    with psycopg.connect(radius_admin_dsn, autocommit=True) as db_conn:
        schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
        with db_conn.cursor() as cur:
            cur.execute(schema_sql)
        print(f"Applied schema from {SCHEMA_FILE.relative_to(SCHEMA_FILE.parents[3])}.")

        with db_conn.cursor() as cur:
            cur.execute(f'GRANT CONNECT ON DATABASE "{RADIUS_DB_NAME}" TO "{RADIUS_ROLE}"')
            cur.execute(f'GRANT USAGE ON SCHEMA public TO "{RADIUS_ROLE}"')
            cur.execute(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public '
                f'TO "{RADIUS_ROLE}"'
            )
            cur.execute(
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{RADIUS_ROLE}"'
            )
        print(f"Granted {RADIUS_ROLE!r} least-privilege access to the RADIUS tables.")

    _write_env(password)
    print(f"Wrote RADIUS_DATABASE_URL to {ENV_FILE} (password not printed).")

    # Verify as the app role itself, not the superuser — proves the grants
    # actually work, not just that the superuser can see the tables.
    app_dsn = f"postgresql://{RADIUS_ROLE}:{password}@{RADIUS_HOST}:{RADIUS_PORT}/{RADIUS_DB_NAME}"
    try:
        with psycopg.connect(app_dsn) as verify_conn, verify_conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ANY(%s)",
                (EXPECTED_TABLES,),
            )
            found = {row[0] for row in cur.fetchall()}
    except psycopg.OperationalError as exc:
        print(f"Verification connection as {RADIUS_ROLE!r} failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    missing = [t for t in EXPECTED_TABLES if t not in found]
    print()
    print("RADIUS local database -- safe summary")
    print(f"  host:     {RADIUS_HOST}")
    print(f"  port:     {RADIUS_PORT}")
    print(f"  database: {RADIUS_DB_NAME}")
    print(f"  role:     {RADIUS_ROLE}")
    print(f"  tables:   {len(found)}/{len(EXPECTED_TABLES)} verified ({', '.join(sorted(found))})")
    if missing:
        print(f"  MISSING:  {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(1)
    print("  status:   OK")


if __name__ == "__main__":
    main()
