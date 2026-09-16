"""Selcom Business API request signing — developer.selcom.business.

    signature = Base64(
        RSA-SHA256-PKCS1v15(
            key = our RSA private key,
            message = f"timestamp={timestamp}&{field1}={value1}&{field2}={value2}...",
        )
    )

sent as four headers alongside the request:

    api-key:       our issued API key
    timestamp:     ISO 8601 UTC with milliseconds, e.g. "2026-05-27T06:01:03.273Z"
    digest:        the base64 signature above
    signed-fields:  comma-separated field names, in the EXACT order used to
                    build the signing string (never including "timestamp"
                    itself — that's always implicit and first)

Field order is identical for GET (query params) and POST (JSON body) —
the caller passes an ordered mapping of exactly the fields it is sending,
in the order it wants signed; this module never reorders them.
"""

import base64
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.integrations.selcom_business.errors import SelcomBusinessAPIError


def _iso8601_utc_millis(when: datetime | None = None) -> str:
    moment = when or datetime.now(UTC)
    # Truncate to milliseconds (3 fractional digits) and force the "Z"
    # suffix the docs show, rather than "+00:00".
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def canonical_signing_string(*, timestamp: str, fields: "OrderedDict[str, str]") -> str:
    parts = [f"timestamp={timestamp}"]
    parts += [f"{name}={value}" for name, value in fields.items()]
    return "&".join(parts)


def _load_private_key(pem_text: str) -> RSAPrivateKey:
    key = serialization.load_pem_private_key(pem_text.encode("utf-8"), password=None)
    if not isinstance(key, RSAPrivateKey):
        raise SelcomBusinessAPIError("Configured Selcom Business private key is not an RSA key")
    return key


@dataclass(frozen=True)
class SignedRequestHeaders:
    api_key: str
    timestamp: str
    digest: str
    signed_fields: str  # comma-separated, in signing order

    def as_dict(self, *, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "api-key": self.api_key,
            "timestamp": self.timestamp,
            "digest": self.digest,
            "signed-fields": self.signed_fields,
        }
        if content_type:
            headers["content-type"] = content_type
        return headers


def sign_request(
    *,
    api_key: str,
    private_key_pem: str,
    fields: "OrderedDict[str, str]",
    when: datetime | None = None,
) -> SignedRequestHeaders:
    """`fields` must already be in the exact order to sign (never includes
    "timestamp" — that's added implicitly and first) and every value must
    be the exact string that will be sent on the wire (query param or JSON
    field value), since the signature covers those exact bytes."""
    timestamp = _iso8601_utc_millis(when)
    message = canonical_signing_string(timestamp=timestamp, fields=fields).encode("utf-8")

    private_key = _load_private_key(private_key_pem)
    signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())

    digest = base64.b64encode(signature).decode("ascii")
    return SignedRequestHeaders(
        api_key=api_key,
        timestamp=timestamp,
        digest=digest,
        signed_fields=",".join(fields.keys()),
    )
