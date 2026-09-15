"use client";

import { Receipt } from "lucide-react";
import { DataTable, MoneyDisplay, StatusBadge, type StatusVariant } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface TransactionRow {
  id: string;
  reference: string;
  channel: string | null;
  amount: string;
  status: string;
  created_at: string;
}

interface TransactionListResponse {
  success: boolean;
  data: TransactionRow[];
}

const STATUS_VARIANT: Record<string, StatusVariant> = {
  completed: "success",
  pending: "pending",
  failed: "danger",
};

/** The 5 most recent customer payments for this tenant — see
 * GET /api/v1/payments (already tenant-scoped, already sorted newest
 * first by BaseRepository's default_sort). */
export function RecentTransactionsTable() {
  const { state, data, error, refetch } = useApiQuery<TransactionListResponse>(
    "/api/v1/payments?page_size=5",
  );

  const rows = data?.data ?? [];
  const tableState = state === "loading" ? "loading" : state === "error" ? "error" : rows.length === 0 ? "empty" : "success";

  return (
    <DataTable
      columns={[
        { key: "reference", header: "Reference" },
        { key: "channel", header: "Channel", render: (row) => row.channel ?? "—" },
        {
          key: "amount",
          header: "Amount",
          align: "right",
          render: (row) => <MoneyDisplay amount={row.amount} />,
        },
        {
          key: "status",
          header: "Status",
          render: (row) => (
            <StatusBadge variant={STATUS_VARIANT[row.status] ?? "neutral"} label={row.status} />
          ),
        },
        {
          key: "created_at",
          header: "Date",
          align: "right",
          render: (row) =>
            new Date(row.created_at).toLocaleString("en-TZ", {
              dateStyle: "medium",
              timeStyle: "short",
              timeZone: "Africa/Dar_es_Salaam",
            }),
        },
      ]}
      rows={rows}
      state={tableState}
      emptyState={{
        icon: <Receipt size={24} />,
        title: "No transactions yet",
        description: "Completed and failed payments will appear here.",
      }}
      errorState={{
        title: "Unable to load transactions",
        description: error?.message,
        onRetry: refetch,
      }}
    />
  );
}
