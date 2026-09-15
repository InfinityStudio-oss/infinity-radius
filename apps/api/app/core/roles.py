"""RBAC role codes. Mirrors the immutable rows seeded into `public.roles`
by the initial migration — this module is the single source of truth for
role code strings used in Python; the seed migration must stay in sync.
"""

from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    TENANT_OWNER = "TENANT_OWNER"
    TENANT_ADMIN = "TENANT_ADMIN"
    ACCOUNTANT = "ACCOUNTANT"
    NETWORK_TECHNICIAN = "NETWORK_TECHNICIAN"
    CUSTOMER_CARE = "CUSTOMER_CARE"
    CASHIER = "CASHIER"
    # Prepared for the customer-portal auth phase; not yet reachable via
    # Supabase Auth login (customers are not FastAPI/dashboard users today).
    CUSTOMER = "CUSTOMER"


# Every staff role that operates within a single tenant's dashboard —
# i.e. every role except the platform-wide SUPER_ADMIN and the
# not-yet-authenticated CUSTOMER.
TENANT_STAFF_ROLES = (
    Role.TENANT_OWNER,
    Role.TENANT_ADMIN,
    Role.ACCOUNTANT,
    Role.NETWORK_TECHNICIAN,
    Role.CUSTOMER_CARE,
    Role.CASHIER,
)

# Role groups mirroring the ROLE_PERMISSIONS seeded by the rbac_seed_data
# migration — used to build per-endpoint RBAC dependencies without
# re-deriving the same tuples in every router module.
MANAGEMENT_ROLES = (Role.TENANT_OWNER, Role.TENANT_ADMIN)
FINANCE_ROLES = (Role.TENANT_OWNER, Role.TENANT_ADMIN, Role.ACCOUNTANT)
FRONTLINE_ROLES = (Role.TENANT_OWNER, Role.TENANT_ADMIN, Role.CUSTOMER_CARE, Role.CASHIER)
NETWORK_ROLES = (Role.TENANT_OWNER, Role.TENANT_ADMIN, Role.NETWORK_TECHNICIAN)
