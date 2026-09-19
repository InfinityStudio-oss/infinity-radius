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
# (https://developers.selcommobile.com/#get-order-status, re-confirmed
# against the live docs 2026-09-19) — used defensively, an unrecognized
# value is never assumed safe.
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

# A real, documented spelling inconsistency in Selcom's own docs: the
# #get-order-status section's payment_status table spells this
# "USERCANCELLED" (double L), but the #webhook-callback section's own
# payment_status description spells the same concept "USERCANCELED"
# (single L). Accepted as an alias for PAYMENT_STATUS_USERCANCELLED —
# never invented, both spellings are directly Selcom-documented, just in
# two different sections.
PAYMENT_STATUS_USERCANCELED_WEBHOOK_SPELLING = "USERCANCELED"

# NOT part of Selcom's documented payment_status enum above (re-confirmed
# live 2026-09-19) — mapped defensively in app/services/collections.py so
# that IF a real/future Selcom response ever uses one of these plausible
# values, it resolves to a clean terminal status instead of falling
# through to AMBIGUOUS. Never presented anywhere as confirmed Selcom
# behavior — see docs/architecture.md's Collection section.
PAYMENT_STATUS_DECLINED_UNDOCUMENTED = "DECLINED"
PAYMENT_STATUS_FAILED_UNDOCUMENTED = "FAILED"
PAYMENT_STATUS_EXPIRED_UNDOCUMENTED = "EXPIRED"
