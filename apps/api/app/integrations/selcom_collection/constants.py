"""Endpoint paths for Selcom Mobile Checkout — https://developers.selcommobile.com/
(#checkout-api, #create-order-minimal, #process-order-wallet-pull-payment,
#get-order-status). Paths only ever come from the official docs, never
invented — see app/integrations/selcom_collection/client.py for how the
configured base URL is joined with these.
"""

CREATE_ORDER_MINIMAL_PATH = "/v1/checkout/create-order-minimal"
WALLET_PAYMENT_PATH = "/v1/checkout/wallet-payment"
ORDER_STATUS_PATH = "/v1/checkout/order-status"

# Documented order-status `payment_status` values
# (https://developers.selcommobile.com/#get-order-status) — used
# defensively, an unrecognized value is never assumed safe.
PAYMENT_STATUS_PENDING = "PENDING"
PAYMENT_STATUS_COMPLETED = "COMPLETED"
PAYMENT_STATUS_CANCELLED = "CANCELLED"
PAYMENT_STATUS_USERCANCELLED = "USERCANCELLED"
PAYMENT_STATUS_REJECTED = "REJECTED"
PAYMENT_STATUS_INPROGRESS = "INPROGRESS"

KNOWN_PAYMENT_STATUSES = frozenset(
    {
        PAYMENT_STATUS_PENDING,
        PAYMENT_STATUS_COMPLETED,
        PAYMENT_STATUS_CANCELLED,
        PAYMENT_STATUS_USERCANCELLED,
        PAYMENT_STATUS_REJECTED,
        PAYMENT_STATUS_INPROGRESS,
    }
)
