/**
 * Presentation rules for Collection statuses.
 *
 * Mirrors app/core/enums.py.CollectionStatus, but is deliberately NOT a
 * closed union at runtime: the backend can introduce a status (or a
 * provider can surface an unrecognised one) before this build knows about
 * it, so every lookup falls back to an explicit "needs review" shape
 * rather than throwing or — far worse — defaulting to something that reads
 * as success or as a plain failure.
 *
 * Copy rule: never tell a tenant money has arrived before the local status
 * is COMPLETED. Everything short of that is phrased as still in flight.
 */

import type { StatusVariant } from "@infinity-radius/ui";

export const COLLECTION_STATUSES = [
  "CREATED",
  "STK_SENT",
  "PENDING",
  "INPROGRESS",
  "REQUIRES_REVIEW",
  "COMPLETED",
  "CANCELLED",
  "USERCANCELLED",
  "REJECTED",
  "DECLINED",
  "FAILED",
  "EXPIRED",
  "AMBIGUOUS",
] as const;

export type CollectionStatus = (typeof COLLECTION_STATUSES)[number];

/** Tone drives both the badge colour and how prominent the row feels. */
export type CollectionTone = "progress" | "success" | "attention" | "failure" | "unknown";

export interface CollectionStatusPresentation {
  /** Short label for badges and table cells. */
  label: string;
  /** Full sentence shown on the detail view. */
  message: string;
  tone: CollectionTone;
  variant: StatusVariant;
  /** Non-terminal locally: the dashboard should keep polling. */
  isPolling: boolean;
  /** True only when funds are confirmed — gates all "paid" wording. */
  isPaid: boolean;
}

const PRESENTATION: Record<CollectionStatus, CollectionStatusPresentation> = {
  CREATED: {
    label: "Created",
    message: "Payment request created.",
    tone: "progress",
    variant: "neutral",
    isPolling: true,
    isPaid: false,
  },
  STK_SENT: {
    label: "Sent to phone",
    message: "Payment request sent to the customer's phone.",
    tone: "progress",
    variant: "pending",
    isPolling: true,
    isPaid: false,
  },
  PENDING: {
    label: "Pending",
    message: "Waiting for the mobile-money provider to confirm the payment.",
    tone: "progress",
    variant: "pending",
    isPolling: true,
    isPaid: false,
  },
  INPROGRESS: {
    label: "Processing",
    message: "Payment is being processed by the mobile-money provider.",
    tone: "progress",
    variant: "pending",
    isPolling: true,
    isPaid: false,
  },
  REQUIRES_REVIEW: {
    label: "Checking",
    message:
      "Provider confirmation is taking longer than usual. Infinity Radius is still checking this payment automatically.",
    tone: "attention",
    variant: "warning",
    isPolling: true,
    isPaid: false,
  },
  COMPLETED: {
    label: "Completed",
    message: "Payment completed successfully.",
    tone: "success",
    variant: "success",
    isPolling: false,
    isPaid: true,
  },
  CANCELLED: {
    label: "Cancelled",
    message: "Payment request was cancelled.",
    tone: "failure",
    variant: "neutral",
    isPolling: false,
    isPaid: false,
  },
  USERCANCELLED: {
    label: "Cancelled by customer",
    message: "The customer cancelled the payment.",
    tone: "failure",
    variant: "neutral",
    isPolling: false,
    isPaid: false,
  },
  REJECTED: {
    label: "Rejected",
    message: "The payment was rejected.",
    tone: "failure",
    variant: "danger",
    isPolling: false,
    isPaid: false,
  },
  DECLINED: {
    label: "Declined",
    message: "The payment was declined.",
    tone: "failure",
    variant: "danger",
    isPolling: false,
    isPaid: false,
  },
  FAILED: {
    label: "Failed",
    message: "The payment failed.",
    tone: "failure",
    variant: "danger",
    isPolling: false,
    isPaid: false,
  },
  EXPIRED: {
    label: "Expired",
    message: "The payment request expired.",
    tone: "failure",
    variant: "neutral",
    isPolling: false,
    isPaid: false,
  },
  AMBIGUOUS: {
    label: "Checking",
    message:
      "Infinity Radius received an unexpected provider response. The payment is being checked automatically. Do not create a duplicate request.",
    tone: "attention",
    variant: "warning",
    isPolling: true,
    isPaid: false,
  },
};

/**
 * Shown for any status this build doesn't recognise. Keeps polling (the
 * backend may still resolve it) and never claims success or failure.
 */
const UNKNOWN: CollectionStatusPresentation = {
  label: "Needs review",
  message:
    "This payment is in a state Infinity Radius is still checking. Do not create a duplicate request.",
  tone: "unknown",
  variant: "warning",
  isPolling: true,
  isPaid: false,
};

export function isKnownCollectionStatus(status: string): status is CollectionStatus {
  return Object.prototype.hasOwnProperty.call(PRESENTATION, status);
}

/** Never throws — an unrecognised or empty status yields the UNKNOWN shape. */
export function presentCollectionStatus(
  status: string | null | undefined,
): CollectionStatusPresentation {
  if (!status || !isKnownCollectionStatus(status)) return UNKNOWN;
  return PRESENTATION[status];
}

/** Whether the dashboard should keep refreshing this transaction. */
export function shouldPollCollection(status: string | null | undefined): boolean {
  return presentCollectionStatus(status).isPolling;
}
