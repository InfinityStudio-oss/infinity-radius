"""Selcom Mobile Checkout request signing/verification —
https://developers.selcommobile.com/#authentication.

Deliberately independent from app/integrations/selcom_business/signing.py
— a different Selcom product, a different Authorization format, a
different timestamp format, and (unlike Business, which is RSA-only)
two possible digest methods. The two integrations must never share a
signer, a header shape, or a secret.

    Authorization: SELCOM <Base64(api_key)>
    Timestamp:     ISO 8601 with a UTC offset, e.g. "2019-02-26T09:30:46+03:00"
    Digest-Method: HS256 | RS256
    Digest:        Base64(HMAC_SHA256(signing_string, api_secret))          [HS256]
                   Base64(RSA_SHA256_PKCS1v15(signing_string, private_key)) [RS256]
    Signed-Fields: comma-separated field names, in the EXACT order used to
                   build the signing string (timestamp is always implicit
                   and first, never itself listed)

    signing_string = f"timestamp={timestamp}&{field1}={value1}&{field2}={value2}..."

DOCUMENTATION CONFLICT (see docs/architecture.md): the Authentication
section's own worked example uses full ISO 8601 with a UTC offset
("2019-02-26T09:30:46+03:00"), but every individual endpoint's curl
sample instead shows the header value as the literal placeholder
"{timestamp in yyyy-dd-mm H:i:s format}" — a different, non-ISO shape,
and internally inconsistent even in its own field order (yyyy-dd-mm is
neither Y-m-d nor d-m-Y). We follow the Authentication section's
concrete, unambiguous worked example (full ISO 8601 with offset) as the
authoritative rule, since a placeholder string is not evidence of a real
format. We use a UTC ("+00:00") offset specifically — the docs constrain
the *shape*, not the *zone*, and UTC avoids DST/locale ambiguity.
"""

import base64
import hashlib
import hmac
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.integrations.selcom_collection.errors import (
    SelcomCollectionAPIError,
    SelcomCollectionWebhookVerificationError,
)

_HEADER_AUTHORIZATION = "Authorization"
_HEADER_TIMESTAMP = "Timestamp"
_HEADER_DIGEST_METHOD = "Digest-Method"
_HEADER_DIGEST = "Digest"
_HEADER_SIGNED_FIELDS = "Signed-Fields"


def _iso8601_with_offset(when: datetime | None = None) -> str:
    moment = (when or datetime.now(UTC)).astimezone(UTC)
    return moment.isoformat(timespec="seconds")


def canonical_signing_string(*, timestamp: str, fields: "OrderedDict[str, str]") -> str:
    parts = [f"timestamp={timestamp}"]
    parts += [f"{name}={value}" for name, value in fields.items()]
    return "&".join(parts)


def _load_rsa_private_key(pem_text: str) -> RSAPrivateKey:
    key = serialization.load_pem_private_key(pem_text.encode("utf-8"), password=None)
    if not isinstance(key, RSAPrivateKey):
        raise SelcomCollectionAPIError("Configured Selcom Collection private key is not an RSA key")
    return key


def _digest_hs256(*, api_secret: str, message: bytes) -> str:
    signature = hmac.new(api_secret.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.b64encode(signature).decode("ascii")


def _digest_rs256(*, private_key_pem: str, message: bytes) -> str:
    private_key = _load_rsa_private_key(private_key_pem)
    signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


@dataclass(frozen=True)
class SignedRequestHeaders:
    authorization: str
    timestamp: str
    digest_method: str
    digest: str
    signed_fields: str  # comma-separated, in signing order

    def as_dict(self) -> dict[str, str]:
        return {
            _HEADER_AUTHORIZATION: self.authorization,
            _HEADER_TIMESTAMP: self.timestamp,
            _HEADER_DIGEST_METHOD: self.digest_method,
            _HEADER_DIGEST: self.digest,
            _HEADER_SIGNED_FIELDS: self.signed_fields,
        }


def sign_request(
    *,
    api_key: str,
    digest_method: str,
    api_secret: str | None,
    private_key_pem: str | None,
    fields: "OrderedDict[str, str]",
    when: datetime | None = None,
) -> SignedRequestHeaders:
    """`fields` must already be in the exact order to sign (never includes
    "timestamp" itself — that's added implicitly and first) and every
    value must be the exact string sent on the wire (query param or JSON
    field value), since the signature covers those exact bytes."""
    timestamp = _iso8601_with_offset(when)
    message = canonical_signing_string(timestamp=timestamp, fields=fields).encode("utf-8")

    if digest_method == "HS256":
        if not api_secret:
            raise SelcomCollectionAPIError("HS256 signing requires api_secret")
        digest = _digest_hs256(api_secret=api_secret, message=message)
    elif digest_method == "RS256":
        if not private_key_pem:
            raise SelcomCollectionAPIError("RS256 signing requires private_key_pem")
        digest = _digest_rs256(private_key_pem=private_key_pem, message=message)
    else:
        raise SelcomCollectionAPIError(f"Unsupported digest method: {digest_method!r}")

    return SignedRequestHeaders(
        authorization=f"SELCOM {base64.b64encode(api_key.encode('utf-8')).decode('ascii')}",
        timestamp=timestamp,
        digest_method=digest_method,
        digest=digest,
        signed_fields=",".join(fields.keys()),
    )


def compute_digest_for_verification(
    *,
    digest_method: str,
    api_secret: str | None,
    private_key_pem: str | None,
    timestamp: str,
    signed_field_names: list[str],
    field_values: "OrderedDict[str, str]",
) -> str:
    """The verifier-side counterpart of sign_request — used to check an
    INBOUND Selcom webhook's own Digest header. `signed_field_names` is
    whatever Selcom's own Signed-Fields header declared (never a
    hardcoded assumption of which fields are signed); `field_values` must
    contain the exact string value of every one of those field names as
    received in the webhook body."""
    ordered = OrderedDict((name, field_values[name]) for name in signed_field_names)
    message = canonical_signing_string(timestamp=timestamp, fields=ordered).encode("utf-8")
    if digest_method == "HS256":
        if not api_secret:
            raise SelcomCollectionAPIError("HS256 verification requires api_secret")
        return _digest_hs256(api_secret=api_secret, message=message)
    if digest_method == "RS256":
        # RS256 verification would use the PUBLIC key, not our own
        # private key — Selcom's docs do not publish a public key for
        # verifying THEIR signature (RS256 as documented is for signing
        # OUR outbound requests, where we hold the private key). If a
        # real RS256-signed webhook is ever received, this must be
        # implemented against Selcom's published public key, never
        # guessed — see docs/architecture.md.
        raise SelcomCollectionAPIError(
            "RS256 webhook verification is not implemented — Selcom has not published a "
            "public key for this; see docs/architecture.md's Collection section."
        )
    raise SelcomCollectionAPIError(f"Unsupported digest method: {digest_method!r}")


# Generous but not unbounded — Selcom's docs don't state a mandatory
# freshness window for Checkout webhooks specifically (unlike this
# platform's own internal HMAC scheme, which documents one explicitly),
# so this is defense-in-depth, not a documented requirement. Wide enough
# that a real webhook is never rejected for merely being a little slow.
DEFAULT_WEBHOOK_MAX_SKEW_SECONDS = 300


def verify_webhook_request(
    *,
    api_key: str,
    digest_method: str,
    api_secret: str | None,
    private_key_pem: str | None,
    headers: dict[str, str],
    body_fields: "OrderedDict[str, str]",
    max_skew_seconds: int = DEFAULT_WEBHOOK_MAX_SKEW_SECONDS,
) -> None:
    """Verifies an INBOUND Selcom Collection webhook — raises
    SelcomCollectionWebhookVerificationError on any failure, never
    returns a value on success (the caller only needs to know
    verification passed). `body_fields` must be every field present in
    the parsed webhook JSON body, as strings, keyed by field name — this
    function only ever signs/checks the subset the webhook's OWN
    Signed-Fields header declares, exactly as sent, never a hardcoded
    assumption of which fields are signed.

    `headers` lookups are case-insensitive: ASGI/Starlette delivers
    inbound request headers as lowercase (`dict(request.headers)` in
    app/api/v1/webhooks.py), while this module's own outbound
    SignedRequestHeaders.as_dict() emits them Title-Cased — matching
    HTTP's own case-insensitive semantics rather than assuming either
    caller's casing convention."""
    headers_lower = {key.lower(): value for key, value in headers.items()}
    expected_authorization = f"SELCOM {base64.b64encode(api_key.encode('utf-8')).decode('ascii')}"
    authorization = headers_lower.get(_HEADER_AUTHORIZATION.lower())
    if not authorization or not hmac.compare_digest(authorization, expected_authorization):
        raise SelcomCollectionWebhookVerificationError("Authorization header did not match")

    received_digest_method = headers_lower.get(_HEADER_DIGEST_METHOD.lower())
    if received_digest_method != digest_method:
        raise SelcomCollectionWebhookVerificationError(
            f"Digest-Method {received_digest_method!r} does not match configured {digest_method!r}"
        )

    timestamp = headers_lower.get(_HEADER_TIMESTAMP.lower())
    digest = headers_lower.get(_HEADER_DIGEST.lower())
    signed_fields_header = headers_lower.get(_HEADER_SIGNED_FIELDS.lower())
    if not timestamp or not digest or not signed_fields_header:
        raise SelcomCollectionWebhookVerificationError("Missing Timestamp/Digest/Signed-Fields")

    try:
        request_time = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise SelcomCollectionWebhookVerificationError("Unparseable Timestamp header") from exc
    if request_time.tzinfo is None:
        request_time = request_time.replace(tzinfo=UTC)
    if abs((datetime.now(UTC) - request_time).total_seconds()) > max_skew_seconds:
        raise SelcomCollectionWebhookVerificationError("Timestamp outside tolerance")

    signed_field_names = [name.strip() for name in signed_fields_header.split(",") if name.strip()]
    missing = [name for name in signed_field_names if name not in body_fields]
    if missing:
        raise SelcomCollectionWebhookVerificationError(
            f"Signed-Fields references field(s) not present in body: {missing}"
        )

    try:
        expected_digest = compute_digest_for_verification(
            digest_method=digest_method,
            api_secret=api_secret,
            private_key_pem=private_key_pem,
            timestamp=timestamp,
            signed_field_names=signed_field_names,
            field_values=body_fields,
        )
    except SelcomCollectionAPIError as exc:
        raise SelcomCollectionWebhookVerificationError(str(exc)) from exc

    if not hmac.compare_digest(expected_digest, digest):
        raise SelcomCollectionWebhookVerificationError("Digest did not match")
