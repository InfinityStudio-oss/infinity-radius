"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Building2, CheckCircle2, XCircle } from "lucide-react";
import {
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  SegmentedTabs,
  type DataTableColumn,
} from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface AdminTenantQueueRow {
  id: string;
  business_name: string;
  owner_name: string | null;
  owner_email: string | null;
  owner_missing: boolean;
  business_type: string | null;
  region: string | null;
  email_verified: boolean;
  submitted_at: string | null;
  status: string;
}

interface QueueEnvelope {
  success: boolean;
  data: AdminTenantQueueRow[];
}

const FILTERS = [
  { value: "PENDING_VERIFICATION", label: "Pending Verification" },
  { value: "ACTIVE", label: "Active" },
  { value: "REJECTED", label: "Rejected" },
  { value: "SUSPENDED", label: "Suspended" },
  { value: "all", label: "All" },
] as const;

const STATUS_STYLES: Record<string, string> = {
  PENDING_VERIFICATION: "bg-warning/15 text-warning",
  ACTIVE: "bg-success/15 text-success",
  MORE_INFORMATION_REQUIRED: "bg-warning/15 text-warning",
  REJECTED: "bg-error/15 text-error",
  SUSPENDED: "bg-error/15 text-error",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLES[status] ?? "bg-surface-container-high text-on-surface-variant"}`}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}

export default function TenantsQueuePage() {
  const [filter, setFilter] = useState<string>("PENDING_VERIFICATION");
  const { state, data, error, refetch } = useApiQuery<QueueEnvelope>(
    `/api/v1/admin/tenants?status=${filter}`,
  );

  const columns: DataTableColumn<AdminTenantQueueRow & { id: string }>[] = [
    { key: "business_name", header: "Business" },
    {
      key: "owner_name",
      header: "Owner",
      render: (row) =>
        row.owner_missing ? (
          <span className="text-warning inline-flex items-center gap-1 text-xs font-medium">
            <AlertTriangle size={14} />
            Owner record missing
          </span>
        ) : (
          <div className="flex flex-col">
            <span>{row.owner_name ?? "—"}</span>
            {row.owner_email && (
              <span className="text-on-surface-variant text-xs">{row.owner_email}</span>
            )}
          </div>
        ),
    },
    { key: "business_type", header: "Business Type", render: (row) => row.business_type ?? "—" },
    { key: "region", header: "Region", render: (row) => row.region ?? "—" },
    {
      key: "email_verified",
      header: "Email Verified",
      render: (row) =>
        row.email_verified ? (
          <CheckCircle2 size={16} className="text-success" />
        ) : (
          <XCircle size={16} className="text-outline" />
        ),
    },
    {
      key: "submitted_at",
      header: "Submitted",
      render: (row) => (row.submitted_at ? new Date(row.submitted_at).toLocaleDateString() : "—"),
    },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (row) => (
        <Link
          href={`/super-admin/tenants/${row.id}`}
          className="text-primary text-xs font-semibold hover:underline"
        >
          Review
        </Link>
      ),
    },
  ];

  if (state === "error") {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Tenants" description="ISP and hotspot providers on the platform." />
        <ErrorState title="Unable to load tenants" description={error?.message} onRetry={refetch} />
      </div>
    );
  }

  const rows = (data?.data ?? []).map((row) => ({ ...row, id: row.id }));
  const tableState = state === "loading" ? "loading" : rows.length === 0 ? "empty" : "success";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Tenants" description="ISP and hotspot providers on the platform." />

      <SegmentedTabs options={[...FILTERS]} value={filter} onChange={setFilter} />

      {tableState === "empty" ? (
        <EmptyState
          icon={<Building2 size={28} />}
          title="No tenants found"
          description="No tenants match this filter yet."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          state={tableState}
          emptyState={{ title: "No tenants found" }}
        />
      )}
    </div>
  );
}
