"""app/integrations/selcom_collection/signing.py — Selcom Mobile Checkout's
digest-based authentication (https://developers.selcommobile.com/#authentication).
Deliberately pure-function tests — no DB, no HTTP, no client — since every
outbound request and inbound webhook ultimately depends on this module
alone being correct.
"""

import base64
import hashlib
import hmac
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.selcom_collection.errors import (
    SelcomCollectionAPIError,
    SelcomCollectionWebhookVerificationError,
)
from app.integrations.selcom_collection.signing import (
    canonical_signing_string,
    compute_digest_for_verification,
    sign_request,
    verify_webhook_request,
)

_API_KEY = "test-api-key"
_API_SECRET = "test-api-secret"


def test_canonical_signing_string_puts_timestamp_first_and_preserves_field_order() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1"), ("amount", "1000")])
    result = canonical_signing_string(timestamp="2026-09-19T12:00:00+00:00", fields=fields)
    assert result == "timestamp=2026-09-19T12:00:00+00:00&order_id=col-1&amount=1000"


def test_sign_request_hs256_authorization_header_is_base64_of_the_api_key() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    signed = sign_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        fields=fields,
    )
    expected = f"SELCOM {base64.b64encode(_API_KEY.encode('utf-8')).decode('ascii')}"
    assert signed.authorization == expected


def test_sign_request_hs256_digest_matches_manual_hmac_computation() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1"), ("amount", "1000")])
    when = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
    signed = sign_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        fields=fields,
        when=when,
    )
    message = canonical_signing_string(timestamp=signed.timestamp, fields=fields).encode("utf-8")
    expected_digest = base64.b64encode(
        hmac.new(_API_SECRET.encode("utf-8"), message, hashlib.sha256).digest()
    ).decode("ascii")
    assert signed.digest == expected_digest


def test_sign_request_timestamp_is_iso8601_with_utc_offset() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    when = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
    signed = sign_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        fields=fields,
        when=when,
    )
    assert signed.timestamp == "2026-09-19T12:00:00+00:00"


def test_sign_request_signed_fields_header_is_comma_joined_in_signing_order() -> None:
    fields: OrderedDict[str, str] = OrderedDict(
        [("transid", "txn-1"), ("order_id", "col-1"), ("msisdn", "255712345678")]
    )
    signed = sign_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        fields=fields,
    )
    assert signed.signed_fields == "transid,order_id,msisdn"
    # timestamp is implicit/first — never itself listed in Signed-Fields.
    assert "timestamp" not in signed.signed_fields


def test_sign_request_hs256_requires_api_secret() -> None:
    with pytest.raises(SelcomCollectionAPIError):
        sign_request(
            api_key=_API_KEY,
            digest_method="HS256",
            api_secret=None,
            private_key_pem=None,
            fields=OrderedDict(),
        )


def test_sign_request_rs256_requires_private_key() -> None:
    with pytest.raises(SelcomCollectionAPIError):
        sign_request(
            api_key=_API_KEY,
            digest_method="RS256",
            api_secret=None,
            private_key_pem=None,
            fields=OrderedDict(),
        )


def test_sign_request_rejects_unsupported_digest_method() -> None:
    with pytest.raises(SelcomCollectionAPIError):
        sign_request(
            api_key=_API_KEY,
            digest_method="MD5",
            api_secret=_API_SECRET,
            private_key_pem=None,
            fields=OrderedDict(),
        )


def test_sign_request_rs256_digest_matches_manual_rsa_verification() -> None:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    when = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
    signed = sign_request(
        api_key=_API_KEY,
        digest_method="RS256",
        api_secret=None,
        private_key_pem=pem,
        fields=fields,
        when=when,
    )
    message = canonical_signing_string(timestamp=signed.timestamp, fields=fields).encode("utf-8")
    public_key = private_key.public_key()
    # Raises if the signature doesn't verify — no exception is the assertion.
    public_key.verify(
        base64.b64decode(signed.digest), message, padding.PKCS1v15(), hashes.SHA256()
    )


# ------------------------------------------------------- webhook verification


def _sign_webhook_fields(
    *, fields: "OrderedDict[str, str]", when: datetime | None = None
) -> tuple[dict[str, str], "OrderedDict[str, str]"]:
    signed = sign_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        fields=fields,
        when=when,
    )
    return signed.as_dict(), fields


def test_verify_webhook_request_accepts_a_genuinely_valid_signature() -> None:
    fields: OrderedDict[str, str] = OrderedDict(
        [("order_id", "col-1"), ("result", "SUCCESS"), ("payment_status", "COMPLETED")]
    )
    headers, body_fields = _sign_webhook_fields(fields=fields)
    # Must return None / not raise — this is the exact bug class fixed
    # 2026-09-19: a stray unconditional `raise` after the digest check
    # would have rejected every genuinely valid webhook.
    result = verify_webhook_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        headers=headers,
        body_fields=body_fields,
    )
    assert result is None


def test_verify_webhook_request_rejects_wrong_authorization_header() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    headers, body_fields = _sign_webhook_fields(fields=fields)
    headers["Authorization"] = f"SELCOM {base64.b64encode(b'someone-else').decode('ascii')}"
    with pytest.raises(SelcomCollectionWebhookVerificationError):
        verify_webhook_request(
            api_key=_API_KEY,
            digest_method="HS256",
            api_secret=_API_SECRET,
            private_key_pem=None,
            headers=headers,
            body_fields=body_fields,
        )


def test_verify_webhook_request_rejects_tampered_digest() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    headers, body_fields = _sign_webhook_fields(fields=fields)
    headers["Digest"] = base64.b64encode(b"not-the-real-signature").decode("ascii")
    with pytest.raises(SelcomCollectionWebhookVerificationError):
        verify_webhook_request(
            api_key=_API_KEY,
            digest_method="HS256",
            api_secret=_API_SECRET,
            private_key_pem=None,
            headers=headers,
            body_fields=body_fields,
        )


def test_verify_webhook_request_rejects_tampered_body_field_after_signing() -> None:
    """The Digest covers the exact field VALUES — changing order_id after
    signing must invalidate the signature even though Signed-Fields still
    lists the same field names."""
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1"), ("amount", "1000")])
    headers, body_fields = _sign_webhook_fields(fields=fields)
    tampered = OrderedDict(body_fields)
    tampered["amount"] = "999999"
    with pytest.raises(SelcomCollectionWebhookVerificationError):
        verify_webhook_request(
            api_key=_API_KEY,
            digest_method="HS256",
            api_secret=_API_SECRET,
            private_key_pem=None,
            headers=headers,
            body_fields=tampered,
        )


def test_verify_webhook_request_rejects_digest_method_mismatch() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    headers, body_fields = _sign_webhook_fields(fields=fields)
    headers["Digest-Method"] = "RS256"
    with pytest.raises(SelcomCollectionWebhookVerificationError):
        verify_webhook_request(
            api_key=_API_KEY,
            digest_method="HS256",  # configured method
            api_secret=_API_SECRET,
            private_key_pem=None,
            headers=headers,
            body_fields=body_fields,
        )


def test_verify_webhook_request_accepts_lowercase_header_keys() -> None:
    """ASGI/Starlette delivers real inbound request headers as lowercase
    (dict(request.headers) in app/api/v1/webhooks.py) — verification must
    not silently reject a genuinely valid webhook just because the
    caller's headers dict uses lowercase keys rather than the Title-Case
    this module's own as_dict() happens to emit for outbound requests."""
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    headers, body_fields = _sign_webhook_fields(fields=fields)
    lowercase_headers = {key.lower(): value for key, value in headers.items()}
    result = verify_webhook_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        headers=lowercase_headers,
        body_fields=body_fields,
    )
    assert result is None


def test_verify_webhook_request_rejects_missing_headers() -> None:
    with pytest.raises(SelcomCollectionWebhookVerificationError):
        verify_webhook_request(
            api_key=_API_KEY,
            digest_method="HS256",
            api_secret=_API_SECRET,
            private_key_pem=None,
            headers={},
            body_fields=OrderedDict(),
        )


def test_verify_webhook_request_rejects_stale_timestamp() -> None:
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    stale_time = datetime.now(UTC) - timedelta(seconds=3600)
    headers, body_fields = _sign_webhook_fields(fields=fields, when=stale_time)
    with pytest.raises(SelcomCollectionWebhookVerificationError):
        verify_webhook_request(
            api_key=_API_KEY,
            digest_method="HS256",
            api_secret=_API_SECRET,
            private_key_pem=None,
            headers=headers,
            body_fields=body_fields,
            max_skew_seconds=300,
        )


def test_verify_webhook_request_rejects_signed_field_not_present_in_body() -> None:
    """Signed-Fields references a field name whose value was never actually
    supplied in body_fields — must never guess a value to fill the gap."""
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    headers, body_fields = _sign_webhook_fields(fields=fields)
    headers["Signed-Fields"] = "order_id,amount"  # "amount" isn't in body_fields
    with pytest.raises(SelcomCollectionWebhookVerificationError):
        verify_webhook_request(
            api_key=_API_KEY,
            digest_method="HS256",
            api_secret=_API_SECRET,
            private_key_pem=None,
            headers=headers,
            body_fields=body_fields,
        )


def test_verify_webhook_request_only_checks_fields_signed_fields_actually_names() -> None:
    """An extra, unsigned field present in the body (e.g. "channel", which
    Selcom's own docs say is NOT part of Signed-Fields) must never break
    verification — only the fields Signed-Fields names are checked."""
    fields: OrderedDict[str, str] = OrderedDict([("order_id", "col-1")])
    headers, body_fields = _sign_webhook_fields(fields=fields)
    body_fields_with_extra = OrderedDict(body_fields)
    body_fields_with_extra["channel"] = "MPESA"
    result = verify_webhook_request(
        api_key=_API_KEY,
        digest_method="HS256",
        api_secret=_API_SECRET,
        private_key_pem=None,
        headers=headers,
        body_fields=body_fields_with_extra,
    )
    assert result is None


def test_compute_digest_for_verification_rs256_is_not_implemented() -> None:
    """Selcom has not published a public key to verify an RS256-signed
    webhook — this must fail loudly, never silently accept/skip
    verification."""
    with pytest.raises(SelcomCollectionAPIError):
        compute_digest_for_verification(
            digest_method="RS256",
            api_secret=None,
            private_key_pem=None,
            timestamp="2026-09-19T12:00:00+00:00",
            signed_field_names=["order_id"],
            field_values=OrderedDict([("order_id", "col-1")]),
        )


def test_compute_digest_for_verification_rejects_unsupported_digest_method() -> None:
    with pytest.raises(SelcomCollectionAPIError):
        compute_digest_for_verification(
            digest_method="MD5",
            api_secret=_API_SECRET,
            private_key_pem=None,
            timestamp="2026-09-19T12:00:00+00:00",
            signed_field_names=["order_id"],
            field_values=OrderedDict([("order_id", "col-1")]),
        )
