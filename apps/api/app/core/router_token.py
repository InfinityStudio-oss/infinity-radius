"""Signed public router token — the only thing a captive-portal redirect
URL is ever allowed to carry to identify a router (see
app/api/v1/public.py): `router=<token>&mac=<client-mac>&dst=<destination>`.
Never a tenant_id, never a raw router UUID in cleartext.

Fernet gives us both properties a public identifier here needs: it's
authenticated (a client can't forge a token for a router it wasn't issued,
or tamper with one) and encrypted (the router UUID inside isn't even
visible, just in case that ever matters for a future router). Keyed by
ROUTER_TOKEN_SIGNING_KEY — deliberately separate from
SECRETS_ENCRYPTION_KEY (app.core.crypto) since this token is baked into a
router's own hotspot configuration and is handed to the (semi-trusted)
network, whereas the secrets key must never leave the server.

The token has no expiry: it's provisioned once per router (see
RouterProvisioningService.get_public_token) and lives in that router's
static hotspot login redirect for as long as the router is in service.
"""

from functools import lru_cache
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().router_token_signing_key.encode("utf-8"))


def create_router_token(router_id: UUID) -> str:
    return _fernet().encrypt(str(router_id).encode("utf-8")).decode("utf-8")


def resolve_router_token(token: str) -> UUID | None:
    """Returns the router UUID the token was issued for, or None if the
    token is invalid/tampered/unrecognized — never raises, since this is
    called on fully untrusted public input."""
    try:
        raw = _fernet().decrypt(token.encode("utf-8"))
        return UUID(raw.decode("utf-8"))
    except (InvalidToken, ValueError):
        return None
