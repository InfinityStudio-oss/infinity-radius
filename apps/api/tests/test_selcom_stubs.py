"""Every real outbound Selcom operation (order creation, status query,
request signing/auth, webhook signature verification) is a documented
TODO pending official Selcom API documentation — these tests prove each
one fails LOUDLY and typed (never silently "succeeds" or returns a
guessed value), and that the two failure modes (missing credentials vs.
code genuinely not implemented yet) are distinguishable.
"""

from decimal import Decimal

import pytest

from app.integrations.selcom.authentication import SelcomAuthenticator
from app.integrations.selcom.client import SelcomClient
from app.integrations.selcom.config import SelcomConfig
from app.integrations.selcom.disbursement import SelcomDisbursementService
from app.integrations.selcom.exceptions import SelcomNotConfiguredError, SelcomNotImplementedError
from app.integrations.selcom.schemas import CollectionOrderRequest, DisbursementOrderRequest
from app.integrations.selcom.signatures import sign_request, verify_webhook_signature

_UNCONFIGURED = SelcomConfig(api_base_url=None, api_key=None, api_secret=None, merchant_id=None)
_CONFIGURED = SelcomConfig(
    api_base_url="https://example.test",
    api_key="test-key",
    api_secret="test-secret",
    merchant_id="test-merchant",
)


def test_selcom_disbursement_enabled_defaults_to_false() -> None:
    """The real, safe-by-default value — independent of
    tests/conftest.py's SELCOM_DISBURSEMENT_ENABLED=true override, which
    exists only so the rest of this suite can exercise the gated
    maker-checker/submission code paths (see app/services/payouts.py)."""
    from app.core.config import Settings

    assert Settings.model_fields["selcom_disbursement_enabled"].default is False


async def test_initiate_collection_without_credentials_raises_not_configured() -> None:
    client = SelcomClient(_UNCONFIGURED)
    with pytest.raises(SelcomNotConfiguredError):
        await client.collection.initiate_collection(
            CollectionOrderRequest(
                reference="ref",
                amount=Decimal("1000"),
                currency="TZS",
                customer_phone="255712345678",
            )
        )


async def test_initiate_collection_with_credentials_raises_not_implemented() -> None:
    """Configured credentials alone can never make this succeed — the
    request/response schema itself is still undocumented."""
    client = SelcomClient(_CONFIGURED)
    with pytest.raises(SelcomNotImplementedError):
        await client.collection.initiate_collection(
            CollectionOrderRequest(
                reference="ref",
                amount=Decimal("1000"),
                currency="TZS",
                customer_phone="255712345678",
            )
        )


async def test_query_collection_raises_not_implemented() -> None:
    client = SelcomClient(_CONFIGURED)
    with pytest.raises(SelcomNotImplementedError):
        await client.collection.query_collection(provider_reference="anything")


async def test_initiate_disbursement_without_credentials_raises_not_configured() -> None:
    service = SelcomDisbursementService(_UNCONFIGURED)
    with pytest.raises(SelcomNotConfiguredError):
        await service.initiate_disbursement(
            DisbursementOrderRequest(
                reference="ref", amount=Decimal("1000"), currency="TZS",
                recipient_phone="255712345678",
            )
        )


async def test_disbursement_raises_not_implemented() -> None:
    service = SelcomDisbursementService(_CONFIGURED)
    with pytest.raises(SelcomNotImplementedError):
        await service.initiate_disbursement(
            DisbursementOrderRequest(
                reference="ref", amount=Decimal("1000"), currency="TZS",
                recipient_phone="255712345678",
            )
        )
    with pytest.raises(SelcomNotImplementedError):
        await service.query_disbursement(provider_reference="anything")


async def test_disbursement_verify_callback_never_returns_true_on_a_guess() -> None:
    service = SelcomDisbursementService(_CONFIGURED)
    with pytest.raises(SelcomNotImplementedError):
        service.verify_callback(headers={}, body=b"{}")


def test_build_auth_headers_raises_not_implemented() -> None:
    authenticator = SelcomAuthenticator(_CONFIGURED)
    with pytest.raises(SelcomNotImplementedError):
        authenticator.build_auth_headers(method="POST", path="/whatever", body=b"{}")


def test_build_auth_headers_without_credentials_raises_not_configured() -> None:
    authenticator = SelcomAuthenticator(_UNCONFIGURED)
    with pytest.raises(SelcomNotConfiguredError):
        authenticator.build_auth_headers(method="POST", path="/whatever", body=b"{}")


def test_sign_request_raises_not_implemented() -> None:
    with pytest.raises(SelcomNotImplementedError):
        sign_request(config=_CONFIGURED, method="POST", path="/whatever", body=b"{}")


def test_verify_webhook_signature_never_returns_true_on_a_guess() -> None:
    """The most important guarantee in this whole module: nobody can
    forge a "payment succeeded" callback by relying on this silently
    passing before a real check exists."""
    with pytest.raises(SelcomNotImplementedError):
        verify_webhook_signature(config=_CONFIGURED, headers={}, body=b"{}")
