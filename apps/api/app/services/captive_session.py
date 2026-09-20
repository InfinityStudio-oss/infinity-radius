"""Issues and validates captive payment sessions — the server-side half of
the short-lived intent token a hotspot customer holds.

WHY A DATABASE ROW AND NOT JUST A TOKEN
A stateless token cannot be made single-use, and cannot be revoked. The
`captive_sessions` row is what makes both possible: `nonce` is UNIQUE, so
a replayed issuance cannot create a second session, and `consumed_at`
records that a session has been spent. Expiry is checked twice —
cryptographically by the token's TTL and in the database by `expires_at` —
so surviving one is not enough.

WHAT THE BROWSER CAN AND CANNOT INFLUENCE
The browser supplies a router token and, at payment time, an intent token,
a package_id and a phone number. It never supplies a tenant_id, an amount,
a price, a currency or a payment_provider, and none of those are fields on
any request model — they are resolved here and in the payment service from
the session's own router row. A customer tampering with the request can
change WHICH package they are asking for; they cannot change what it
costs, who gets paid, or which tenant they belong to.

A MAC address is treated as a correlation hint only, never as
authentication: it is trivially spoofable and is frequently absent
(randomized MACs, or a redirect that did not carry one).
"""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.captive_intent_token import (
    CaptiveIntentNotConfiguredError,
    create_captive_intent_token,
    resolve_captive_intent_token,
)
from app.core.config import get_settings
from app.core.errors import DomainValidationError
from app.models.network import CaptiveSession
from app.repositories.network import RouterRepository
from app.services.audit import write_audit_log

logger = structlog.get_logger("services.captive_session")


class CaptiveSessionError(Exception):
    """A captive session could not be issued or validated.

    Deliberately one error type for every rejection reason — expired,
    forged, already consumed, unknown router — so a client probing the
    endpoint cannot tell which part of its input was wrong.
    """


class CaptivePortalSessionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.router_repo = RouterRepository(db)

    async def issue(
        self, *, router_id: UUID, mac_address: str | None = None
    ) -> tuple[str, CaptiveSession]:
        """Creates one captive session for an already-resolved router and
        returns its intent token.

        `router_id` MUST come from a verified router token (see
        app/core/router_token.py) — this method never accepts a raw router
        id from a client, and the tenant is read from the router row here
        rather than being supplied.
        """
        settings = get_settings()

        # tenant_id=None: the router token is the only thing establishing
        # which router — and therefore which tenant — this is about.
        router = await self.router_repo.get_by_id(tenant_id=None, id=router_id)
        if router is None:
            raise CaptiveSessionError("Router not found")

        now = datetime.now(UTC)
        session = CaptiveSession(
            tenant_id=router.tenant_id,
            router_id=router.id,
            # Correlation/troubleshooting only — never trusted as identity.
            mac_address=mac_address,
            # 256 bits from secrets: the UNIQUE constraint makes a
            # collision a hard failure rather than a silent overwrite.
            nonce=secrets.token_urlsafe(32),
            expires_at=now + timedelta(seconds=settings.captive_intent_token_ttl_seconds),
        )
        self.db.add(session)
        await self.db.flush()

        try:
            token = create_captive_intent_token(session.id)
        except CaptiveIntentNotConfiguredError as exc:
            raise CaptiveSessionError(str(exc)) from exc

        await write_audit_log(
            self.db,
            tenant_id=router.tenant_id,
            actor_id=None,
            action="captive_portal.session_issued",
            target_type="captive_session",
            target_id=session.id,
            # No token, no nonce — an audit row must never contain a value
            # that would let a reader replay the session it describes.
            metadata={"router_id": str(router.id), "mac_present": mac_address is not None},
        )
        return token, session

    async def resolve(self, *, intent_token: str) -> CaptiveSession:
        """Validates an intent token and returns its session.

        Every rejection raises the same error type with a deliberately
        uninformative message. Checks, in order: token authenticity + TTL,
        session exists, not already consumed, not expired by the database
        clock.
        """
        session_id = resolve_captive_intent_token(intent_token)
        if session_id is None:
            raise CaptiveSessionError("Invalid or expired captive session")

        session = (
            await self.db.execute(
                select(CaptiveSession).where(CaptiveSession.id == session_id)
            )
        ).scalar_one_or_none()
        if session is None:
            raise CaptiveSessionError("Invalid or expired captive session")

        if session.consumed_at is not None:
            # Single use. A refresh or a second tab replaying the same
            # token must not be able to start a second payment.
            raise CaptiveSessionError("Invalid or expired captive session")

        # Second, independent expiry check — the token's own TTL is
        # cryptographic and this one is the database's clock. A token that
        # somehow survives one must still fail the other.
        if session.expires_at <= datetime.now(UTC):
            raise CaptiveSessionError("Invalid or expired captive session")

        return session

    async def consume(self, *, session: CaptiveSession) -> None:
        """Marks a session spent. Called once a payment attempt has
        genuinely been created for it."""
        session.consumed_at = datetime.now(UTC)
        await self.db.flush()

    async def resolve_for_router(
        self, *, intent_token: str, expected_router_id: UUID | None = None
    ) -> CaptiveSession:
        """resolve(), plus an optional check that the session belongs to
        the router the caller thinks it does — defence against pairing a
        valid session from one site with another site's context."""
        session = await self.resolve(intent_token=intent_token)
        if expected_router_id is not None and session.router_id != expected_router_id:
            raise CaptiveSessionError("Invalid or expired captive session")
        return session


def validate_package_ownership(*, package_tenant_id: UUID, session_tenant_id: UUID) -> None:
    """The cross-tenant guard, stated once so both the payment service and
    its tests use the same rule.

    A package is only purchasable through a session belonging to the same
    tenant. Package lookups are already tenant-scoped, so this is a second
    line of defence rather than the only one.
    """
    if package_tenant_id != session_tenant_id:
        raise DomainValidationError("package_id does not belong to this router's tenant")
