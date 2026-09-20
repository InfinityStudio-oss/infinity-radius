/**
 * Customer-facing captive portal flow logic, kept out of the component so
 * the rules that actually matter can be tested without rendering.
 *
 * The one rule worth stating up front: a customer whose payment is still
 * being verified must never be told it failed, and must never be invited
 * to pay again. REQUIRES_REVIEW and AMBIGUOUS can still settle, so a
 * second payment on top of one that later succeeds is a real double
 * charge. The backend signals that with `under_review`; everything here
 * treats it as the highest-priority state.
 *
 * No provider host, no signing, no Selcom anything lives in this app. The
 * browser only ever talks to Infinity Radius's own API.
 */

/** Mirrors apps/api/app/schemas/captive_portal.py — keep in sync by hand. */
export type PaymentStatus = "pending" | "completed" | "failed" | "not_found";
export type ActivationStatus = "pending" | "activating" | "active" | "failed";

export interface PaymentStatusResult {
  status: PaymentStatus;
  under_review?: boolean;
  activation_status?: ActivationStatus | null;
  package_name?: string | null;
  amount?: string | null;
  currency?: string | null;
  payer_phone_masked?: string | null;
  provider_reference?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  activated_at?: string | null;
  message?: string | null;
  login_username?: string | null;
  login_password?: string | null;
}

export type InitiateStatus =
  | "pending"
  | "duplicate"
  | "provider_not_configured"
  | "unavailable"
  | "rate_limited";

export interface PaymentInitiateResult {
  transaction_token: string | null;
  status: InitiateStatus;
  amount?: string | null;
  currency?: string | null;
  message?: string | null;
}

/**
 * What the waiting screen should show. Deliberately a small closed set —
 * the provider's own status vocabulary is never exposed to a customer.
 */
export type ScreenState =
  | "waiting" // STK sent, nothing decided yet
  | "under-review" // still being verified — do NOT pay again
  | "activating" // paid; access being set up
  | "active" // paid and online
  | "activation-failed" // paid, access not granted, support notified
  | "failed"; // payment genuinely did not happen

export function screenStateFor(result: PaymentStatusResult): ScreenState {
  // Checked FIRST, before `status`, because an under-review payment is
  // reported as "pending" and must never fall through to a retry prompt.
  if (result.under_review) return "under-review";

  if (result.status === "failed" || result.status === "not_found") return "failed";
  if (result.status !== "completed") return "waiting";

  switch (result.activation_status) {
    case "active":
      return "active";
    case "failed":
      return "activation-failed";
    default:
      // pending/activating/absent — paid, access on the way.
      return "activating";
  }
}

/**
 * Whether the customer may deliberately start a NEW payment attempt.
 *
 * Only from a genuinely terminal, unsuccessful payment. Never while a
 * payment is under review (it may still settle), and never when they have
 * already paid — an activation failure is ours to fix, not something to
 * charge them again for.
 */
export function canRetryPayment(state: ScreenState): boolean {
  return state === "failed";
}

/** True once there is nothing left to poll for. */
export function isTerminalState(state: ScreenState): boolean {
  return state === "active" || state === "failed" || state === "activation-failed";
}

const POLL_BASE_MS = 3_000;
const POLL_MAX_MS = 30_000;

/**
 * Polling interval with backoff.
 *
 * Starts responsive, because most STK approvals land within seconds, then
 * backs off so a customer who walks away does not leave a tab hammering
 * the API for hours. A payment stuck under review can legitimately take a
 * very long time — production has seen ~6.5h — so the ceiling matters.
 */
export function pollIntervalMs(attempt: number): number {
  if (attempt <= 3) return POLL_BASE_MS;
  const backed = POLL_BASE_MS * 2 ** (attempt - 3);
  return Math.min(backed, POLL_MAX_MS);
}

/** Loose client-side check only — normalize_tz_phone on the backend is the
 *  real validator, and the only one that decides what gets charged. */
export function isPlausibleTzSubscriberNumber(digits: string): boolean {
  return /^[67]\d{8}$/.test(digits);
}

/** Digits a customer may type, before the fixed +255 prefix. */
export function sanitizeSubscriberInput(raw: string): string {
  return raw.replace(/\D/g, "").slice(0, 9);
}

/** Formats a TZS amount for the confirmation screen. */
export function formatTzs(amount: string | null | undefined): string {
  if (!amount) return "—";
  const value = Number(amount);
  if (Number.isNaN(value)) return amount;
  return new Intl.NumberFormat("en-TZ", { maximumFractionDigits: 0 }).format(value);
}

/** Human-readable package validity, from the package's duration. */
export function formatDuration(minutes: number | null | undefined): string {
  if (!minutes || minutes <= 0) return "No time limit";
  if (minutes < 60) return `${minutes} minutes`;
  const hours = minutes / 60;
  if (hours < 24) {
    return Number.isInteger(hours) ? `${hours} hour${hours === 1 ? "" : "s"}` : `${hours.toFixed(1)} hours`;
  }
  const days = hours / 24;
  return Number.isInteger(days) ? `${days} day${days === 1 ? "" : "s"}` : `${days.toFixed(1)} days`;
}
