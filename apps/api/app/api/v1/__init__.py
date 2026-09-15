from fastapi import APIRouter

from app.api.v1.admin_diagnostics import router as admin_diagnostics_router
from app.api.v1.admin_tenants import router as admin_tenants_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.customers import router as customers_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.locations import router as locations_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.packages import router as packages_router
from app.api.v1.payments import router as payments_router
from app.api.v1.payouts import router as payouts_router
from app.api.v1.public import router as public_router
from app.api.v1.reports import router as reports_router
from app.api.v1.routers_module import router as network_routers_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.super_admin import router as super_admin_router
from app.api.v1.system import router as system_router
from app.api.v1.tenant import router as tenant_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.vouchers import router as vouchers_router
from app.api.v1.wallet import router as wallet_router
from app.api.v1.webhooks import router as webhooks_router

api_router = APIRouter()

# --- Production core modules (Router -> Service -> Repository -> DB) -------
api_router.include_router(system_router, prefix="/system", tags=["system"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(tenants_router, prefix="/tenants", tags=["tenants"])
api_router.include_router(customers_router, prefix="/customers", tags=["customers"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(locations_router, prefix="/locations", tags=["locations"])
api_router.include_router(network_routers_router, prefix="/routers", tags=["routers"])
api_router.include_router(packages_router, prefix="/packages", tags=["packages"])
api_router.include_router(subscriptions_router, prefix="/subscriptions", tags=["subscriptions"])
api_router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
api_router.include_router(vouchers_router, prefix="/vouchers", tags=["vouchers"])
api_router.include_router(payments_router, prefix="/payments", tags=["payments"])
api_router.include_router(wallet_router, prefix="/wallet", tags=["wallet"])
api_router.include_router(payouts_router, prefix="/payouts", tags=["payouts"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
api_router.include_router(audit_router, prefix="/audit", tags=["audit"])

# --- Client signup + business onboarding (unauthenticated) and the Super
# Admin approval workflow that follows it (SUPER_ADMIN-only) -----------
api_router.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(admin_tenants_router, prefix="/admin/tenants", tags=["admin-tenants"])
api_router.include_router(
    admin_diagnostics_router, prefix="/admin/diagnostics", tags=["admin-diagnostics"]
)

# --- Inbound payment-provider callbacks (no Supabase auth — see
# app/api/v1/webhooks.py for how authenticity is established instead) ----
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])

# --- Earlier-phase surfaces, kept for the dashboard shell's existing calls --
# (generic not_configured placeholders for resources not yet listed above;
# see app/api/v1/tenant.py and super_admin.py docstrings)
api_router.include_router(tenant_router, prefix="/tenant", tags=["tenant-legacy"])
api_router.include_router(super_admin_router, prefix="/super-admin", tags=["super-admin"])
api_router.include_router(public_router, prefix="/public", tags=["public"])
