"use client";

import { Banknote } from "lucide-react";
import { DataTable, MoneyDisplay, StatusBadge } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface PendingPayoutRow {
  withdrawal_id: string;
  tenant_name: string;
  amount_tzs: string;
  status: string;
  requested_at: string;
}

interface PendingPayoutsResponse {
  success: boolean;
  data: PendingPayoutRow[];
}

/** Real withdrawals awaiting maker-checker approval, across every tenant —
 * see GET /api/v1/super-admin/pending-payouts. */
export function PendingPayoutsPanel() {
  const { state, data, error, refetch } = useApiQuery<PendingPayoutsResponse>(
    "/api/v1/super-admin/pending-payouts",
  );

  const rows = (data?.data ?? []).map((row) => ({ ...row, id: row.withdrawal_id }));
  const tableState =
    state === "loading" ? "loading" : state === "error" ? "error" : rows.length === 0 ? "empty" : "success";

  return (
    <DataTable
      columns={[
        { key: "tenant_name", header: "Tenant" },
        {
          key: "amount_tzs",
          header: "Amount",
          align: "right",
          render: (row) => <MoneyDisplay amount={row.amount_tzs} />,
        },
        {
          key: "status",
          header: "Status",
          render: (row) => (
            <StatusBadge
              variant={row.status === "APPROVED" ? "success" : "pending"}
              label={row.status.replaceAll("_", " ")}
            />
          ),
        },
        {
          key: "requested_at",
          header: "Requested",
          align: "right",
          render: (row) =>
            new Date(row.requested_at).toLocaleString("en-TZ", {
              dateStyle: "medium",
              timeStyle: "short",
              timeZone: "Africa/Dar_es_Salaam",
            }),
        },
      ]}
      rows={rows}
      state={tableState}
      emptyState={{
        icon: <Banknote size={24} />,
        title: "No pending payouts",
        description: "Withdrawals awaiting approval across all tenants will appear here.",
      }}
      errorState={{
        title: "Unable to load pending payouts",
        description: error?.message,
        onRetry: refetch,
      }}
    />
  );
}
