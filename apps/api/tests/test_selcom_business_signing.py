"""Selcom Business RSA-SHA256 request signing. Uses a throwaway test
keypair generated once per test run — never production key material.
"""

from collections import OrderedDict
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.integrations.selcom_business.signing import canonical_signing_string, sign_request

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_KEY_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("utf-8")
_PUBLIC_KEY = _PRIVATE_KEY.public_key()

_OTHER_PRIVATE_KEY_PEM = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    .decode("utf-8")
)


def _verify(*, message: bytes, digest_b64: str) -> bool:
    import base64

    try:
        _PUBLIC_KEY.verify(
            base64.b64decode(digest_b64), message, padding.PKCS1v15(), hashes.SHA256()
        )
        return True
    except Exception:  # noqa: BLE001 — test helper, any failure means "invalid"
        return False


def test_canonical_signing_string_puts_timestamp_first_then_signed_fields_in_order() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("bank", "CRDB"), ("account", "0123456789")])
    result = canonical_signing_string(timestamp="2026-05-27T06:01:03.273Z", fields=fields)
    assert result == "timestamp=2026-05-27T06:01:03.273Z&bank=CRDB&account=0123456789"


def test_timestamp_format_is_iso8601_utc_with_milliseconds() -> None:
    when = datetime(2026, 5, 27, 6, 1, 3, 273_000, tzinfo=UTC)
    headers = sign_request(
        api_key="k", private_key_pem=_PRIVATE_KEY_PEM, fields=OrderedDict(), when=when
    )
    assert headers.timestamp == "2026-05-27T06:01:03.273Z"


def test_signature_verifies_against_the_exact_canonical_string() -> None:
    fields: OrderedDict[str, str] = OrderedDict(
        [("transId", "wd-123"), ("recipientFiCode", "CRDB"), ("amount", "50000.00")]
    )
    when = datetime(2026, 1, 1, 12, 0, 0, 0, tzinfo=UTC)
    headers = sign_request(
        api_key="my-api-key", private_key_pem=_PRIVATE_KEY_PEM, fields=fields, when=when
    )
    message = canonical_signing_string(timestamp=headers.timestamp, fields=fields).encode("utf-8")
    assert _verify(message=message, digest_b64=headers.digest)


def test_signed_fields_header_lists_field_names_in_signing_order() -> None:
    fields: OrderedDict[str, str] = OrderedDict(
        [("recipientFiCode", "CRDB"), ("recipientAccount", "0123456789"), ("amount", "1000.00")]
    )
    headers = sign_request(api_key="k", private_key_pem=_PRIVATE_KEY_PEM, fields=fields)
    assert headers.signed_fields == "recipientFiCode,recipientAccount,amount"


def test_as_dict_exposes_exactly_the_four_signing_headers_plus_optional_content_type() -> None:
    headers = sign_request(api_key="k", private_key_pem=_PRIVATE_KEY_PEM, fields=OrderedDict())
    assert set(headers.as_dict()) == {"api-key", "timestamp", "digest", "signed-fields"}
    assert set(headers.as_dict(content_type="application/json")) == {
        "api-key",
        "timestamp",
        "digest",
        "signed-fields",
        "content-type",
    }


def test_changed_field_value_invalidates_the_expected_digest() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("amount", "1000.00")])
    when = datetime(2026, 1, 1, 12, 0, 0, 0, tzinfo=UTC)
    headers = sign_request(api_key="k", private_key_pem=_PRIVATE_KEY_PEM, fields=fields, when=when)

    tampered_fields: OrderedDict[str, str] = OrderedDict([("amount", "9999999.00")])
    tampered_message = canonical_signing_string(
        timestamp=headers.timestamp, fields=tampered_fields
    ).encode("utf-8")
    assert not _verify(message=tampered_message, digest_b64=headers.digest)


def test_signed_by_a_different_key_does_not_verify() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("bank", "CRDB")])
    when = datetime(2026, 1, 1, 12, 0, 0, 0, tzinfo=UTC)
    headers = sign_request(
        api_key="k", private_key_pem=_OTHER_PRIVATE_KEY_PEM, fields=fields, when=when
    )
    message = canonical_signing_string(timestamp=headers.timestamp, fields=fields).encode("utf-8")
    assert not _verify(message=message, digest_b64=headers.digest)


def test_query_parameter_signing_get_style_fields() -> None:
    """Account lookup (GET) signs the same way as a POST body — field
    order/format is identical, only the transport differs."""
    fields: OrderedDict[str, str] = OrderedDict(
        [("bank", "MPESA"), ("account", "255712345678"), ("transId", "lookup-abc")]
    )
    headers = sign_request(api_key="k", private_key_pem=_PRIVATE_KEY_PEM, fields=fields)
    message = canonical_signing_string(timestamp=headers.timestamp, fields=fields).encode("utf-8")
    assert _verify(message=message, digest_b64=headers.digest)


def test_never_uses_production_private_key_material() -> None:
    """Sanity check on this test file itself: the key used throughout is
    generated fresh per test run, never loaded from any env var/settings."""
    assert "SELCOM_BUSINESS_PRIVATE_KEY" not in globals()
    assert _PRIVATE_KEY_PEM.startswith("-----BEGIN PRIVATE KEY-----")


@pytest.mark.parametrize("bad_pem", ["not a pem", "", "-----BEGIN PRIVATE KEY-----\ngarbage\n"])
def test_malformed_private_key_raises(bad_pem: str) -> None:
    with pytest.raises(Exception):  # noqa: B017,PT011 — any load failure is acceptable here
        sign_request(api_key="k", private_key_pem=bad_pem, fields=OrderedDict())
