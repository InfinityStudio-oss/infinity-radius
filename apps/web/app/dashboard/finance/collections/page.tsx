"use client";

import { useCallback, useMemo, useState } from "react";
import { Receipt } from "lucide-react";
import {
  DashboardMetricCard,
  DashboardMetricGridSkeleton,
  DataTable,
  ErrorState,
  MoneyDisplay,
  PageHeader,
  type DataTableColumn,
} from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";
import type {
  ApiEnvelope,
  ApiListEnvelope,
  CollectionSummaryRead,
  TransactionRead,
} from "@/lib/api-types";
import { formatDateTimeShort, orDash } from "@/lib/collections/format";
import { CollectionStatusBadge } from "@/components/dashboard/collections/collection-status-badge";
import { CollectionDetailDrawer } from "@/components/dashboard/collections/collection-detail-drawer";
import { NewCollectionDialog } from "@/components/dashboard/collections/new-collection-dialog";

const PAGE_SIZE = 20;

export default function CollectionsPage() {
  const [page, setPage] = useState(1);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selected, setSelected] = useState<TransactionRead | null>(null);
  /** Bumped after a new request so both queries refetch. */
  const [refreshKey, setRefreshKey] = useState(0);

  // The Collection-specific list, not the generic /payments one: the
  // transactions table is shared with captive-portal payments, so scoping
  // to this payment family happens server-side on transaction_type. The
  // browser never filters by type itself.
  const listPath = `/api/v1/collections?page=${page}&page_size=${PAGE_SIZE}&sort=-created_at&_r=${refreshKey}`;
  const summaryPath = `/api/v1/collections/summary?_r=${refreshKey}`;

  const list = useApiQuery<ApiListEnvelope<TransactionRead>>(listPath);
  const summary = useApiQuery<ApiEnvelope<CollectionSummaryRead>>(summaryPath);

  const onCreated = useCallback(() => {
    setPage(1);
    setRefreshKey((n) => n + 1);
  }, []);

  const rows = useMemo(() => list.data?.data ?? [], [list.data]);
  const meta = list.data?.meta;
  const totals = summary.data?.data;

  const columns: DataTableColumn<TransactionRead & { id: string }>[] = [
    {
      key: "created_at",
      header: "Created",
      render: (row) => (
        <span className="whitespace-nowrap">{formatDateTimeShort(row.created_at)}</span>
      ),
    },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      render: (row) => <MoneyDisplay amount={row.amount} currency={row.currency} />,
    },
    {
      key: "payer_phone_masked",
      header: "Customer",
      render: (row) => <span className="font-mono text-xs">{orDash(row.payer_phone_masked)}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (row) => <CollectionStatusBadge status={row.status} />,
    },
    {
      key: "reference",
      header: "Order ID",
      render: (row) => (
        <span className="font-mono text-xs break-all">{row.reference}</span>
      ),
    },
    {
      key: "provider_reference",
      header: "Mobile Money Ref",
      render: (row) => (
        <span className="font-mono text-xs">{orDash(row.provider_reference)}</span>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (row) => (
        <button
          type="button"
          onClick={() => setSelected(row)}
          className="text-primary text-sm font-medium hover:underline"
        >
          View
        </button>
      ),
    },
  ];

  if (list.state === "error") {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Collections" description={DESCRIPTION} />
        <ErrorState
          title="Unable to load collections"
          description={list.error?.message}
          onRetry={list.refetch}
        />
      </div>
    );
  }

  const tableState =
    list.state === "loading" ? "loading" : rows.length === 0 ? "empty" : "success";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Collections"
        description={DESCRIPTION}
        actions={
          <button
            type="button"
            onClick={() => setDialogOpen(true)}
            className="bg-primary text-on-primary rounded-lg px-4 py-2 text-sm font-semibold"
          >
            Request payment
          </button>
        }
      />

      {/* Counts come from a tenant-scoped aggregate endpoint, never summed
          from the current page — a page holds at most PAGE_SIZE rows. A
          failed summary fetch renders "unavailable", never a fabricated 0. */}
      {summary.state === "loading" ? (
        <DashboardMetricGridSkeleton count={4} />
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <DashboardMetricCard
            label="Total requests"
            value={totals?.total}
            status={totals ? "ok" : "unavailable"}
          />
          <DashboardMetricCard
            label="Completed"
            value={totals?.completed}
            status={totals ? "ok" : "unavailable"}
          />
          <DashboardMetricCard
            label="In progress"
            value={totals?.in_progress}
            status={totals ? "ok" : "unavailable"}
          />
          <DashboardMetricCard
            label="Needs review"
            value={totals?.requires_attention}
            status={totals ? "ok" : "unavailable"}
          />
        </div>
      )}

      <DataTable
        columns={columns}
        rows={rows as (TransactionRead & { id: string })[]}
        state={tableState}
        emptyState={{
          icon: <Receipt size={28} />,
          title: "No payments yet",
          description:
            "Payment requests you send to customers will appear here, with their live status.",
        }}
      />

      {meta && meta.total_pages > 1 && (
        <nav
          className="flex items-center justify-between gap-4"
          aria-label="Collections pagination"
        >
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="border-outline text-on-surface rounded-lg border px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-on-surface-variant text-sm">
            Page {meta.page} of {meta.total_pages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={page >= meta.total_pages}
            className="border-outline text-on-surface rounded-lg border px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Next
          </button>
        </nav>
      )}

      <NewCollectionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={onCreated}
      />
      <CollectionDetailDrawer transaction={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

const DESCRIPTION =
  "Request mobile-money payments from customers and track each request's status.";
