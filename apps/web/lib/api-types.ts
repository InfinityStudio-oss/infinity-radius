/** Mirrors apps/api/app/schemas/common.py — keep these two in sync by hand. */

export type MetricStatus = "ok" | "no_data" | "not_configured" | "unavailable";

export interface MetricValue {
  status: MetricStatus;
  value: number | string | null;
  caption: string | null;
}

export type ResourceStatus = "ok" | "not_configured";

export interface ResourceListResponse {
  items: Record<string, unknown>[];
  total: number;
  status: ResourceStatus;
}

/** Mirrors apps/api/app/schemas/envelope.py's ApiResponse[T]. */
export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  meta?: Record<string, unknown> | null;
}

/** Mirrors apps/api/app/schemas/tenancy.py's CurrentUserRead. */
export interface CurrentUserRead {
  id: string;
  email: string | null;
  full_name: string | null;
  tenant_id: string | null;
  tenant_name: string | null;
  tenant_status: string | null;
  roles: string[];
}

/** Mirrors apps/api/app/schemas/onboarding.py's TenantVerificationRead. */
export interface TenantVerificationRead {
  id: string;
  tenant_id: string;
  status: string;
  submitted_at: string | null;
  email_verified_at: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  more_information_message: string | null;
}

/** Mirrors apps/api/app/schemas/onboarding.py's AccountStatusRead. */
export interface AccountStatusRead {
  tenant_status: string;
  email_verified: boolean;
  verification: TenantVerificationRead | null;
}
