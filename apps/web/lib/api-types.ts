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

/** Mirrors apps/api/app/schemas/envelope.py's PaginationMeta. */
export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/** Mirrors apps/api/app/schemas/envelope.py's ApiListResponse[T]. */
export interface ApiListEnvelope<T> {
  success: boolean;
  data: T[];
  meta: PaginationMeta;
}

/**
 * Mirrors apps/api/app/schemas/finance.py's TransactionRead.
 *
 * Note the deliberate identifier split — these are four different things
 * and the UI must never present them as interchangeable:
 *  - `reference`            our own order id, echoed back by Selcom
 *  - `collection_transid`   our own wallet-payment request id, never echoed
 *  - `provider_reference`   the payment channel's receipt (evidence only)
 *  - `id`                   the internal Infinity Radius row id
 *
 * The raw payer phone is never sent by the API — only `payer_phone_masked`.
 */
export interface TransactionRead {
  id: string;
  tenant_id: string;
  customer_id: string | null;
  subscription_id: string | null;
  reference: string;
  provider_reference: string | null;
  collection_transid: string | null;
  payer_phone_masked: string | null;
  channel: string | null;
  amount: string;
  currency: string;
  status: string;
  provider_resultcode: string | null;
  provider_message: string | null;
  stk_requested_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Mirrors apps/api/app/schemas/finance.py's CollectionSummaryRead. */
export interface CollectionSummaryRead {
  total: number;
  completed: number;
  in_progress: number;
  requires_attention: number;
  failed: number;
  by_status: Record<string, number>;
}
