"""Selcom Business base-URL + endpoint-path composition. The public docs
show the production base URL AS "https://api.selcom.business/v1" while
separately documenting endpoint paths like "/v1/transaction/process" —
naive concatenation would double up the "/v1" segment. build_url must
produce the identical, correct URL regardless of which spelling of the
base URL is configured.
"""

import pytest

from app.integrations.selcom_business.client import build_url


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.selcom.business",
        "https://api.selcom.business/v1",
        "https://api.selcom.business/v1/",
        "https://api.selcom.business/",
    ],
)
def test_build_url_never_doubles_v1(base_url: str) -> None:
    assert (
        build_url(base_url, "/v1/transaction/process")
        == "https://api.selcom.business/v1/transaction/process"
    )


def test_build_url_sandbox_base() -> None:
    assert (
        build_url("https://sandbox.selcom.business", "/v1/account/lookup")
        == "https://sandbox.selcom.business/v1/account/lookup"
    )


def test_build_url_every_documented_endpoint() -> None:
    base = "https://api.selcom.business/v1"
    assert build_url(base, "/v1/account/lookup") == "https://api.selcom.business/v1/account/lookup"
    assert (
        build_url(base, "/v1/transaction/process")
        == "https://api.selcom.business/v1/transaction/process"
    )
    assert (
        build_url(base, "/v1/transaction/query") == "https://api.selcom.business/v1/transaction/query"
    )
    assert build_url(base, "/v1/balance") == "https://api.selcom.business/v1/balance"


def test_build_url_rejects_a_path_missing_the_v1_prefix() -> None:
    with pytest.raises(ValueError, match="must start with '/v1/'"):
        build_url("https://api.selcom.business", "/transaction/process")
