import { HandCoins } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

/**
 * Platform-wide payments across every tenant and BOTH sources.
 *
 * Deliberately provider-scoped in spirit rather than type-scoped: a
 * captive-portal purchase settled through Selcom is reconciled exactly
 * like a staff-requested Collection, so Super Admin — who owns
 * reconciliation — needs to see both. A tenant's own Collections
 * dashboard is the opposite and stays scoped to COLLECTION only.
 *
 * The state this page exists to surface is "paid, but not online":
 * payment COMPLETED with access FAILED. Only an operator can resolve it,
 * and it is invisible if payment and access share one column.
 */

function sourceLabel(value: unknown): string {
  switch (value) {
    case "CAPTIVE_PORTAL":
      return "Captive Portal";
    case "COLLECTION":
      return "Collection";
    default:
      return "—";
  }
}

function accessLabel(row: Record<string, unknown>): string {
  const activation = row.activation_status;
  if (typeof activation !== "string") {
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
      return "FAILED";
    case "REQUIRES_REVIEW":
      return "Needs review";
    default:
      return activation;
  }
}

export default function CollectionsPage() {
  return (
    <ResourceListPage
      title="Payments"
      description="Platform-wide customer payments — staff Collections and captive portal purchases. Watch for payment Completed with Access Failed."
      resourcePath="/api/v1/super-admin/resources/collections"
      columns={[
        { key: "reference", header: "Order ID" },
        { key: "tenant", header: "Tenant" },
        {
          key: "transaction_type",
          header: "Source",
          render: (row) => (
            <span className="text-xs font-medium">{sourceLabel(row.transaction_type)}</span>
          ),
        },
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
          key: "collection_transid",
          header: "Request ID",
          render: (row) => (
            <span className="font-mono text-[0.6875rem]">
              {(row.collection_transid as string) || "—"}
            </span>
          ),
        },
        {
          key: "provider_reference",
          header: "Channel Ref",
          align: "right",
          render: (row) => (
            <span className="font-mono text-[0.6875rem]">
              {(row.provider_reference as string) || "—"}
            </span>
          ),
        },
      ]}
      emptyIcon={<HandCoins size={28} />}
      emptyTitle="No payments yet"
      emptyDescription="Customer payments across all tenants will appear here."
      searchPlaceholder="Search order id…"
    />
  );
}
