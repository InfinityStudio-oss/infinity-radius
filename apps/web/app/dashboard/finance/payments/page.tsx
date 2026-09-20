"use client";

import { Receipt } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

/**
 * Every customer payment, from BOTH sources.
 *
 * Deliberately not the Collections page: that one stays scoped to
 * transaction_type=COLLECTION — payments a staff member requested — so a
 * captive-portal purchase can never appear there or inflate its counts.
 * This page is the opposite, and is where support answers "a customer says
 * they paid and has no internet".
 *
 * That question needs two independent answers, which is why Source and
 * Access are separate columns: a row can be COMPLETED with access FAILED,
 * meaning the money is settled and the customer is still offline. Reading
 * one column would hide exactly the case that matters.
 */

/** Which business flow created the row — not which provider settled it. */
function sourceLabel(value: unknown): string {
  switch (value) {
    case "CAPTIVE_PORTAL":
      return "Captive Portal";
    case "COLLECTION":
      return "Collection";
    default:
      // Rows predating the discriminator. Shown honestly as unknown rather
      // than guessed into one family or the other.
      return "—";
  }
}

/** Access state, kept separate from payment state on purpose. */
function accessLabel(row: Record<string, unknown>): string {
  const activation = row.activation_status;
  if (typeof activation !== "string") {
    // Only captive-portal purchases grant access; a manual Collection has
    // nothing to activate, so blank is correct rather than "pending".
    return row.transaction_type === "CAPTIVE_PORTAL" ? "Not started" : "—";
  }
  switch (activation) {
    case "ACTIVE":
      return "Active";
    case "ACTIVATING":
      return "Activating";
    case "PENDING":
      return "Not started";
    case "FAILED":
      return "Failed";
    case "REQUIRES_REVIEW":
      return "Needs review";
    default:
      return activation;
  }
}

export default function PaymentsPage() {
  return (
    <ResourceListPage
      title="Payments"
      description="Every customer payment — staff-requested Collections and captive portal purchases."
      resourcePath="/api/v1/tenant/resources/payments"
      columns={[
        { key: "reference", header: "Reference" },
        {
          key: "transaction_type",
          header: "Source",
          render: (row) => (
            <span className="text-xs font-medium">{sourceLabel(row.transaction_type)}</span>
          ),
        },
        { key: "payer_phone_masked", header: "Customer" },
        {
          key: "amount",
          header: "Amount",
          align: "right",
          render: (row) => <MoneyDisplay amount={(row.amount as string) ?? null} />,
        },
        { key: "status", header: "Payment" },
        {
          key: "activation_status",
          header: "Access",
          render: (row) => <span className="text-xs">{accessLabel(row)}</span>,
        },
        {
          key: "provider_reference",
          header: "Mobile Money Ref",
          align: "right",
          render: (row) => (
            <span className="font-mono text-xs">
              {(row.provider_reference as string) || "—"}
            </span>
          ),
        },
      ]}
      emptyIcon={<Receipt size={28} />}
      emptyTitle="No payments yet"
      emptyDescription="Customer payments will appear here — both payment requests your team sends and packages bought at your hotspots."
      searchPlaceholder="Search reference…"
    />
  );
}
