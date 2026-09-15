import "server-only";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { apiFetch, ApiClientError } from "@/lib/api-client";
import type { AccountStatusRead, ApiEnvelope, CurrentUserRead } from "@/lib/api-types";

/** Redirects to /login when no authenticated Supabase session exists. Call from a layout. */
export async function requireUser() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return user;
}

/**
 * The database-resolved role/tenant view for the current session — never
 * trusted from the JWT's own claims. Returns null if there's no session or
 * the backend call fails (e.g. FastAPI unreachable), so callers can decide
 * how to degrade rather than this throwing mid-layout.
 */
export async function getCurrentUserView(): Promise<CurrentUserRead | null> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) return null;

  try {
    const envelope = await apiFetch<ApiEnvelope<CurrentUserRead>>("/api/v1/auth/me", {
      accessToken: session.access_token,
    });
    return envelope.data;
  } catch (error) {
    if (error instanceof ApiClientError) return null;
    throw error;
  }
}

const ACCOUNT_STATUS_REDIRECTS: Record<string, string> = {
  PENDING_VERIFICATION: "/account/pending-review",
  MORE_INFORMATION_REQUIRED: "/account/action-required",
  REJECTED: "/account/rejected",
  SUSPENDED: "/account/suspended",
};

/**
 * Layout guard for /dashboard — enforced here AND independently by FastAPI
 * (app.core.context.get_tenant_context): this redirect is a UX nicety, not
 * the actual authorization boundary. A tenant whose status isn't ACTIVE
 * lands on the matching /account/* page instead of a blank/broken dashboard.
 */
export async function requireActiveTenantUser() {
  await requireUser();
  const view = await getCurrentUserView();

  if (view === null) {
    redirect("/login");
  }
  if (view.roles.includes("SUPER_ADMIN")) {
    redirect("/super-admin");
  }
  if (!view.tenant_id || !view.tenant_status) {
    redirect("/login");
  }
  if (view.tenant_status !== "ACTIVE") {
    redirect(ACCOUNT_STATUS_REDIRECTS[view.tenant_status] ?? "/account/pending-review");
  }

  return view;
}

/**
 * Server-side fetch for the /account/* pages — requires a session (post
 * email-confirmation, Supabase's own redirect leaves one) but deliberately
 * does not require an ACTIVE tenant, since a pending/rejected/suspended
 * tenant is exactly who reaches these pages.
 */
export async function getAccountStatus(): Promise<AccountStatusRead | null> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) return null;

  try {
    const envelope = await apiFetch<ApiEnvelope<AccountStatusRead>>(
      "/api/v1/onboarding/account-status",
      { accessToken: session.access_token },
    );
    return envelope.data;
  } catch (error) {
    if (error instanceof ApiClientError) return null;
    throw error;
  }
}

/** Layout guard for /super-admin — same "enforced again by FastAPI" note as above. */
export async function requireSuperAdmin() {
  await requireUser();
  const view = await getCurrentUserView();

  if (view === null || !view.roles.includes("SUPER_ADMIN")) {
    redirect("/dashboard");
  }

  return view;
}
