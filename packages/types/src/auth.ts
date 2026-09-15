/**
 * RBAC role codes. Mirrors apps/api/app/core/roles.Role (Python) and the
 * `public.roles` seed data — keep all three in sync by hand.
 *
 * SUPER_ADMIN operates the platform itself (/super-admin/*); every other
 * staff role operates within a single tenant (/dashboard/*). CUSTOMER is
 * prepared for the customer-portal auth phase and not yet reachable via
 * Supabase Auth login.
 */
export type UserRole =
  | "SUPER_ADMIN"
  | "TENANT_OWNER"
  | "TENANT_ADMIN"
  | "ACCOUNTANT"
  | "NETWORK_TECHNICIAN"
  | "CUSTOMER_CARE"
  | "CASHIER"
  | "CUSTOMER";

export const TENANT_STAFF_ROLES: readonly UserRole[] = [
  "TENANT_OWNER",
  "TENANT_ADMIN",
  "ACCOUNTANT",
  "NETWORK_TECHNICIAN",
  "CUSTOMER_CARE",
  "CASHIER",
];

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  country: string;
  currency: string;
  timezone: string;
  status: string;
  createdAt: string;
}

export interface AuthUser {
  id: string;
  email: string | null;
  tenantId: string | null;
  /** A profile may hold more than one role within its tenant. */
  roles: UserRole[];
}
