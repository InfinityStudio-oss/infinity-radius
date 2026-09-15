"use client";

import { Activity } from "lucide-react";
import { DataTable, StatusBadge, type StatusVariant } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface SessionRow {
  id: string;
  session_identifier: string | null;
  ip_address: string | null;
  status: string;
  started_at: string | null;
  created_at: string;
}

interface SessionListResponse {
  success: boolean;
  data: SessionRow[];
}

const STATUS_VARIANT: Record<string, StatusVariant> = {
  active: "online",
  closed: "neutral",
};

/** The 5 most recent connectivity sessions for this tenant — see
 * GET /api/v1/sessions. Written by the RADIUS accounting integration,
 * which doesn't exist yet, so this is legitimately empty until then. */
export function RecentSessionsTable() {
  const { state, data, error, refetch } = useApiQuery<SessionListResponse>(
    "/api/v1/sessions?page_size=5",
  );

  const rows = data?.data ?? [];
  const tableState = state === "loading" ? "loading" : state === "error" ? "error" : rows.length === 0 ? "empty" : "success";

  return (
    <DataTable
      columns={[
        {
          key: "session_identifier",
          header: "Session",
          render: (row) => row.session_identifier ?? row.id.slice(0, 8),
        },
        { key: "ip_address", header: "IP Address", render: (row) => row.ip_address ?? "—" },
        {
          key: "status",
          header: "Status",
          render: (row) => (
            <StatusBadge variant={STATUS_VARIANT[row.status] ?? "neutral"} label={row.status} />
          ),
        },
        {
          key: "started_at",
          header: "Started",
          align: "right",
          render: (row) =>
            row.started_at
              ? new Date(row.started_at).toLocaleString("en-TZ", {
                  dateStyle: "medium",
                  timeStyle: "short",
                  timeZone: "Africa/Dar_es_Salaam",
                })
              : "—",
        },
      ]}
      rows={rows}
      state={tableState}
      emptyState={{
        icon: <Activity size={24} />,
        title: "No sessions yet",
        description: "Customer connectivity sessions will appear here.",
      }}
      errorState={{
        title: "Unable to load sessions",
        description: error?.message,
        onRetry: refetch,
      }}
    />
  );
}
