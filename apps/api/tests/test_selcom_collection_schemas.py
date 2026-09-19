"""app/integrations/selcom_collection/{client,schemas}.py — pure-function
tests for URL composition, TZS whole-amount handling, and Selcom's own
documented data-shape inconsistencies (list-vs-dict `data`, phone/msisdn
aliasing). No DB, no HTTP.
"""

from decimal import Decimal

import pytest

from app.integrations.selcom_collection.client import build_url, whole_tzs_amount
from app.integrations.selcom_collection.schemas import (
    CreateOrderMinimalResponse,
    OrderStatusData,
    OrderStatusResponse,
    WalletPaymentResponse,
    money_from_provider,
)

# --------------------------------------------------------------- build_url


def test_build_url_appends_path_to_bare_base_url() -> None:
    assert (
        build_url("https://apigwtest.selcommobile.com", "/v1/checkout/order-status")
        == "https://apigwtest.selcommobile.com/v1/checkout/order-status"
    )


def test_build_url_never_doubles_a_trailing_v1_on_the_base_url() -> None:
    assert (
        build_url("https://apigwtest.selcommobile.com/v1", "/v1/checkout/order-status")
        == "https://apigwtest.selcommobile.com/v1/checkout/order-status"
    )


def test_build_url_strips_trailing_slash_on_base_url() -> None:
    assert (
        build_url("https://apigwtest.selcommobile.com/", "/v1/checkout/order-status")
        == "https://apigwtest.selcommobile.com/v1/checkout/order-status"
    )


def test_build_url_rejects_a_path_not_starting_with_v1() -> None:
    with pytest.raises(ValueError, match="must start with '/v1/'"):
        build_url("https://apigwtest.selcommobile.com", "checkout/order-status")


# --------------------------------------------------------- whole_tzs_amount


def test_whole_tzs_amount_formats_a_whole_number_as_a_bare_integer_string() -> None:
    assert whole_tzs_amount(Decimal("8000")) == "8000"


def test_whole_tzs_amount_formats_a_dot_zero_zero_decimal_as_a_bare_integer_string() -> None:
    assert whole_tzs_amount(Decimal("8000.00")) == "8000"


def test_whole_tzs_amount_fails_closed_on_a_fractional_amount() -> None:
    with pytest.raises(ValueError, match="whole number"):
        whole_tzs_amount(Decimal("8000.50"))


# ------------------------------------------------------------ money_from_provider


def test_money_from_provider_handles_none() -> None:
    assert money_from_provider(None) is None


def test_money_from_provider_avoids_float_binary_imprecision() -> None:
    # 0.1 + 0.2 style imprecision must never leak into a Decimal via a
    # naive Decimal(float) construction.
    assert money_from_provider(1000.1) == Decimal("1000.1")


def test_money_from_provider_rejects_a_genuinely_invalid_value() -> None:
    with pytest.raises(ValueError, match="Invalid monetary value"):
        money_from_provider("not-a-number")


# --------------------------------------------------- defensive `data` parsing


def test_create_order_response_accepts_a_single_item_list() -> None:
    response = CreateOrderMinimalResponse.model_validate(
        {
            "reference": "ref-1",
            "resultcode": "000",
            "result": "SUCCESS",
            "message": "Order created",
            "data": [{"payment_gateway_url": "aHR0cHM6Ly9leGFtcGxlLmNvbQ=="}],
        }
    )
    assert response.first is not None
    assert response.first.payment_gateway_url == "aHR0cHM6Ly9leGFtcGxlLmNvbQ=="


def test_create_order_response_accepts_a_bare_dict_data_shape() -> None:
    """Selcom's docs don't guarantee `data` is always a list — a bare
    object must parse just as safely as a single-item list."""
    response = CreateOrderMinimalResponse.model_validate(
        {"reference": "ref-1", "resultcode": "000", "data": {"gateway_buyer_uuid": "abc"}}
    )
    assert response.first is not None
    assert response.first.gateway_buyer_uuid == "abc"


def test_create_order_response_accepts_an_empty_data_list() -> None:
    response = CreateOrderMinimalResponse.model_validate(
        {"reference": "ref-1", "resultcode": "111", "data": []}
    )
    assert response.first is None


def test_create_order_response_accepts_a_missing_data_key_entirely() -> None:
    response = CreateOrderMinimalResponse.model_validate({"reference": "ref-1"})
    assert response.first is None
    assert response.data == []


def test_wallet_payment_response_parses_minimally() -> None:
    response = WalletPaymentResponse.model_validate(
        {"reference": "ref-1", "resultcode": "111", "result": "PENDING", "message": "Wait"}
    )
    assert response.resultcode == "111"
    assert response.data == []


def test_order_status_response_first_property_returns_none_when_empty() -> None:
    response = OrderStatusResponse.model_validate({"reference": "ref-1", "data": []})
    assert response.first is None


# ------------------------------------------------- phone/msisdn field aliasing


def test_order_status_data_accepts_documented_phone_field_name() -> None:
    data = OrderStatusData.model_validate(
        {"order_id": "col-1", "payment_status": "COMPLETED", "phone": "255712345678"}
    )
    assert data.phone == "255712345678"


def test_order_status_data_accepts_msisdn_alias_when_phone_is_absent() -> None:
    """Documentation conflict: the worked example calls this field
    'phone', but the field table calls it 'msisdn' — both must be
    accepted, never invented."""
    data = OrderStatusData.model_validate(
        {"order_id": "col-1", "payment_status": "COMPLETED", "msisdn": "255712345678"}
    )
    assert data.phone == "255712345678"


def test_order_status_data_prefers_phone_over_msisdn_when_both_present() -> None:
    data = OrderStatusData.model_validate(
        {
            "order_id": "col-1",
            "payment_status": "COMPLETED",
            "phone": "255712345678",
            "msisdn": "255799999999",
        }
    )
    assert data.phone == "255712345678"


def test_order_status_data_amount_parses_a_bare_integer() -> None:
    data = OrderStatusData.model_validate(
        {"order_id": "col-1", "payment_status": "COMPLETED", "amount": 8000}
    )
    assert data.amount == Decimal("8000")


def test_order_status_data_amount_is_none_when_absent() -> None:
    data = OrderStatusData.model_validate({"order_id": "col-1", "payment_status": "PENDING"})
    assert data.amount is None
