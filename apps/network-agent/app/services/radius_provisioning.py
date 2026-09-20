"""Writes FreeRADIUS user/group rows on THIS VPS's local PostgreSQL.

WHY THIS LIVES ON THE AGENT AND NOT IN THE BACKEND
FreeRADIUS and its PostgreSQL both run on this VPS. The backend runs on
Railway. The only ways for Railway to provision a RADIUS user are:

  A) give Railway a direct connection to this database, which means
     exposing PostgreSQL to the public internet, or
  B) have Railway ask this agent — which is already the authenticated,
     IP-allowlisted, signed boundary for exactly this kind of privileged
     local operation — to do it.

(A) would punch a hole through the security model the rest of this system
is built on: the whole point of the agent is that the VPS's internals are
never directly reachable. So this is (B). The database connection string
never leaves the VPS, and `localhost` is the only host this module will
ever talk to.

Every operation is an UPSERT, because activation is retried. Re-running a
provisioning call must converge on the same state rather than erroring or
duplicating attributes — see the backend's captive activation retry sweep.

The schema here is stock FreeRADIUS (radcheck/radusergroup/radgroupreply/
radgroupcheck); this agent does not own it and never migrates it.
"""

import psycopg
import structlog
from psycopg import sql

from app.core.config import get_network_agent_settings

logger = structlog.get_logger("services.radius_provisioning")


class RadiusProvisioningError(RuntimeError):
    """A provisioning operation failed. Always surfaced to the backend as
    a failure so activation is recorded FAILED and retried — never
    swallowed, because a silent failure here means a paying customer
    silently has no internet."""


def _connect() -> psycopg.Connection:
    settings = get_network_agent_settings()
    dsn = settings.radius_database_dsn
    if not dsn:
        raise RadiusProvisioningError(
            "RADIUS_DATABASE_DSN is not configured on this agent."
        )
    try:
        return psycopg.connect(dsn, autocommit=False)
    except psycopg.Error as exc:
        raise RadiusProvisioningError(f"Cannot reach the RADIUS database: {exc}") from exc


def group_name(package_id: str) -> str:
    """Mirrors the backend's radius_group_name() exactly — see
    infrastructure/freeradius/schema/mikrotik_attributes.md. If these two
    ever disagree, users are provisioned into a group that carries no
    speed or timeout attributes."""
    return f"pkg_{package_id}"


def sync_package_group(
    *,
    package_id: str,
    download_speed_kbps: int | None,
    upload_speed_kbps: int | None,
    session_timeout_seconds: int | None,
    simultaneous_sessions: int,
) -> None:
    """Upserts the reply/check attributes for one package's RADIUS group.

    Delete-then-insert inside a single transaction: the attribute SET for
    a package is replaced wholesale, so removing a speed limit from a
    package genuinely removes it rather than leaving a stale row behind.
    """
    name = group_name(package_id)
    reply_attributes: list[tuple[str, str]] = []
    if download_speed_kbps and upload_speed_kbps:
        reply_attributes.append(
            ("Mikrotik-Rate-Limit", f"{download_speed_kbps}k/{upload_speed_kbps}k")
        )
    if session_timeout_seconds:
        reply_attributes.append(("Session-Timeout", str(session_timeout_seconds)))

    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (name,))
            cur.execute("DELETE FROM radgroupcheck WHERE groupname = %s", (name,))
            for attribute, value in reply_attributes:
                cur.execute(
                    "INSERT INTO radgroupreply (groupname, attribute, op, value) "
                    "VALUES (%s, %s, ':=', %s)",
                    (name, attribute, value),
                )
            cur.execute(
                "INSERT INTO radgroupcheck (groupname, attribute, op, value) "
                "VALUES (%s, 'Simultaneous-Use', ':=', %s)",
                (name, str(simultaneous_sessions)),
            )
            conn.commit()
    except psycopg.Error as exc:
        raise RadiusProvisioningError(f"Failed to sync package group: {exc}") from exc

    logger.info("radius.group_synced", group=name, attributes=len(reply_attributes))


def provision_user(*, username: str, package_id: str, password: str) -> None:
    """Upserts one customer's credential and group membership so their next
    PAP auth succeeds and picks up the package's attributes."""
    name = group_name(package_id)
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM radcheck WHERE username = %s AND attribute = 'Cleartext-Password'",
                (username,),
            )
            cur.execute(
                "INSERT INTO radcheck (username, attribute, op, value) "
                "VALUES (%s, 'Cleartext-Password', ':=', %s)",
                (username, password),
            )
            cur.execute("DELETE FROM radusergroup WHERE username = %s", (username,))
            cur.execute(
                "INSERT INTO radusergroup (username, groupname, priority) VALUES (%s, %s, 1)",
                (username, name),
            )
            conn.commit()
    except psycopg.Error as exc:
        raise RadiusProvisioningError(f"Failed to provision user: {exc}") from exc

    # Never the password, and never the raw msisdn beyond what FreeRADIUS
    # itself already stores as the username.
    logger.info("radius.user_provisioned", group=name)


def revoke_user(*, username: str) -> None:
    """Removes a customer's credentials so a stale username/password pair
    cannot keep authenticating after access should have ended."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM radcheck WHERE username = %s", (username,))
            cur.execute("DELETE FROM radusergroup WHERE username = %s", (username,))
            conn.commit()
    except psycopg.Error as exc:
        raise RadiusProvisioningError(f"Failed to revoke user: {exc}") from exc
    logger.info("radius.user_revoked")


def ping() -> bool:
    """Cheap reachability probe, so the backend can tell 'RADIUS is not
    configured' apart from 'RADIUS is down' before it starts provisioning."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT 1"))
            cur.fetchone()
        return True
    except RadiusProvisioningError:
        return False
