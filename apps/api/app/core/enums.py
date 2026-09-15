"""Status/type vocabularies shared by the service and schema layers. Kept
here (not duplicated as inline string literals) so a service, a schema, and
a test all reference the same values.
"""

from enum import StrEnum


class SubscriptionStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"


class VoucherStatus(StrEnum):
    UNUSED = "UNUSED"
    USED = "USED"
    EXPIRED = "EXPIRED"
    VOID = "VOID"


class PackageActivationType(StrEnum):
    """immediate: the subscription activates the moment it's created/redeemed.
    first_use: it stays PENDING until something (a future RADIUS session
    start) explicitly calls SubscriptionService.activate()."""

    IMMEDIATE = "immediate"
    FIRST_USE = "first_use"


class PackageStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class LedgerEntryType(StrEnum):
    """Every reason a tenant wallet's buckets can move. See
    app/services/wallet.py for exactly which methods write which type —
    ledger_entries.entry_type has a matching Postgres CHECK constraint."""

    COLLECTION = "COLLECTION"
    TENANT_SHARE = "TENANT_SHARE"
    PLATFORM_FEE = "PLATFORM_FEE"
    REFUND = "REFUND"
    REVERSAL = "REVERSAL"
    DISBURSEMENT = "DISBURSEMENT"
    DISBURSEMENT_REVERSAL = "DISBURSEMENT_REVERSAL"
    ADJUSTMENT = "ADJUSTMENT"


class LedgerDirection(StrEnum):
    """Whether a ledger entry increased or decreased its wallet_bucket.
    None of this is inferred from entry_type alone — it's explicit and
    queryable (sum credits - sum debits per bucket == that bucket's
    current balance)."""

    CREDIT = "credit"
    DEBIT = "debit"


class WalletBucket(StrEnum):
    """Which of TenantWallet's five balance columns a ledger entry moved —
    1:1 with the five *_balance_tzs / total_disbursed_tzs columns. None
    (not a member of this enum) for entries that don't move any tenant
    bucket at all, e.g. PLATFORM_FEE and the informational COLLECTION
    entry."""

    AVAILABLE = "available"
    PENDING = "pending"
    RESERVED = "reserved"
    FROZEN = "frozen"
    TOTAL_DISBURSED = "total_disbursed"


class SettlementMode(StrEnum):
    """How a tenant actually gets paid — see app/services/settlement_config.py.
    Per-tenant, versioned, super-admin managed; defaults to DIRECT_MERCHANT_SETTLEMENT
    when a tenant has no explicit configuration, because Infinity Radius must
    never assume it legally/commercially holds a tenant's funds."""

    # Selcom settles directly with the tenant's own merchant account.
    # Infinity Radius's wallet is informational only — WalletService.
    # request_withdrawal refuses to run for a tenant in this mode.
    DIRECT_MERCHANT_SETTLEMENT = "direct_merchant_settlement"
    # Infinity Radius holds tenant funds in tenant_wallets and disburses on
    # approval via Selcom Disbursement — the full withdrawal/maker-checker
    # flow in app/services/payouts.py applies.
    PLATFORM_MANAGED_WALLET = "platform_managed_wallet"


class WithdrawalStatus(StrEnum):
    """A withdrawal's lifecycle — see app/services/payouts.py for exactly
    which methods cause which transition, and withdrawal_events for the
    full transition history of any one row."""

    DRAFT = "DRAFT"  # created, balance reserved, awaiting 2FA confirmation
    PENDING_APPROVAL = "PENDING_APPROVAL"  # 2FA confirmed, awaiting maker-checker approval
    APPROVED = "APPROVED"  # approved, about to be (or being) submitted to Selcom
    PROCESSING = "PROCESSING"  # submitted to Selcom, awaiting its authoritative result
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"  # Selcom reported failure, or submission itself couldn't happen
    REJECTED = "REJECTED"  # a checker rejected it before submission
    CANCELLED = "CANCELLED"  # the requester cancelled it, or 2FA expired/exhausted
    REVERSED = "REVERSED"  # a completed disbursement was later reversed


# Terminal states — a withdrawal in one of these never transitions again.
WITHDRAWAL_TERMINAL_STATUSES = frozenset(
    {
        WithdrawalStatus.SUCCESS,
        WithdrawalStatus.FAILED,
        WithdrawalStatus.REJECTED,
        WithdrawalStatus.CANCELLED,
        WithdrawalStatus.REVERSED,
    }
)


class TenantStatus(StrEnum):
    """A tenant's own onboarding/approval lifecycle. Mirrors
    TenantVerificationStatus 1:1 except for SUSPENDED, which only exists
    at the tenant level (a suspension acts on an already-approved
    tenant, not on the verification record itself)."""

    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    ACTIVE = "ACTIVE"
    MORE_INFORMATION_REQUIRED = "MORE_INFORMATION_REQUIRED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


class TenantVerificationStatus(StrEnum):
    """A tenant_verifications row's own status — see app/services/admin_tenants.py."""

    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    APPROVED = "APPROVED"
    MORE_INFORMATION_REQUIRED = "MORE_INFORMATION_REQUIRED"
    REJECTED = "REJECTED"


class BusinessType(StrEnum):
    """The onboarding form's Business Type options — see docs/localization.md."""

    ISP = "ISP"
    WISP = "WISP"
    HOTSPOT_OPERATOR = "Hotspot Operator"
    APARTMENT_WIFI = "Apartment WiFi"
    HOTEL_WIFI = "Hotel WiFi"
    CAMPUS_WIFI = "Campus WiFi"
    RESTAURANT_CAFE_WIFI = "Restaurant / Cafe WiFi"
    PROPERTY_MANAGER = "Property Manager"
    PUBLIC_WIFI_OPERATOR = "Public WiFi Operator"
    OTHER = "Other"


class EmailEventType(StrEnum):
    """See app/integrations/resend/service.py for the matching send_* method."""

    VERIFY_EMAIL = "VERIFY_EMAIL"
    NEW_TENANT_ADMIN_ALERT = "NEW_TENANT_ADMIN_ALERT"
    TENANT_APPROVED = "TENANT_APPROVED"
    TENANT_REJECTED = "TENANT_REJECTED"
    MORE_INFORMATION_REQUIRED = "MORE_INFORMATION_REQUIRED"
    TENANT_SUSPENDED = "TENANT_SUSPENDED"
    TENANT_REACTIVATED = "TENANT_REACTIVATED"


class EmailEventStatus(StrEnum):
    SENT = "SENT"
    FAILED = "FAILED"
