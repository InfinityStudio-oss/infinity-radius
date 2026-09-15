"use client";

import { Package as PackageIcon } from "lucide-react";
import { DataTable, MoneyDisplay } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface PackagePerformanceRow {
  package_id: string;
  package_name: string;
  active_subscriptions: number;
  total_subscriptions: number;
  revenue_tzs: string;
}

interface PackagePerformanceResponse {
  success: boolean;
  data: PackagePerformanceRow[];
}

/** Real per-package subscription/revenue ranking for this tenant — see
 * GET /api/v1/dashboard/package-performance. Empty until at least one
 * subscription exists against any package. */
export function PackagePerformancePanel() {
  const { state, data, error, refetch } = useApiQuery<PackagePerformanceResponse>(
    "/api/v1/dashboard/package-performance",
  );

  const rows = (data?.data ?? []).map((row) => ({ ...row, id: row.package_id }));
  const tableState = state === "loading" ? "loading" : state === "error" ? "error" : rows.length === 0 ? "empty" : "success";

  return (
    <DataTable
      columns={[
        { key: "package_name", header: "Package" },
        { key: "active_subscriptions", header: "Active", align: "right" },
        { key: "total_subscriptions", header: "Total", align: "right" },
        {
          key: "revenue_tzs",
          header: "Revenue",
          align: "right",
          render: (row) => <MoneyDisplay amount={row.revenue_tzs} />,
        },
      ]}
      rows={rows}
      state={tableState}
      emptyState={{
        icon: <PackageIcon size={24} />,
        title: "No package activity yet",
        description: "Subscription and revenue performance per package will appear here.",
      }}
      errorState={{
        title: "Unable to load package performance",
        description: error?.message,
        onRetry: refetch,
      }}
    />
  );
}
