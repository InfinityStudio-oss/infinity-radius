"use client";

import { History } from "lucide-react";
import { DataTable } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface AuditLogRow {
  id: string;
  tenant_id: string | null;
  action: string;
  target_type: string | null;
  created_at: string;
}

interface AuditLogListResponse {
  success: boolean;
  data: AuditLogRow[];
}

/** Real, immutable admin/operational events across every tenant — see
 * GET /api/v1/super-admin/audit-logs. */
export function PlatformActivityPanel() {
  const { state, data, error, refetch } = useApiQuery<AuditLogListResponse>(
    "/api/v1/super-admin/audit-logs?page_size=8",
  );

  const rows = data?.data ?? [];
  const tableState =
    state === "loading" ? "loading" : state === "error" ? "error" : rows.length === 0 ? "empty" : "success";

  return (
    <DataTable
      columns={[
        { key: "action", header: "Action" },
        {
          key: "target_type",
          header: "Target",
          render: (row) => row.target_type ?? "—",
        },
        {
          key: "tenant_id",
          header: "Tenant",
          render: (row) => (row.tenant_id ? row.tenant_id.slice(0, 8) : "Platform"),
        },
        {
          key: "created_at",
          header: "When",
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
        icon: <History size={24} />,
        title: "No activity yet",
        description: "Administrative and operational events across every tenant will appear here.",
      }}
      errorState={{
        title: "Unable to load platform activity",
        description: error?.message,
        onRetry: refetch,
      }}
    />
  );
}
