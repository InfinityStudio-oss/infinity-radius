"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { MoneyDisplay, DataTable, StatusBadge, PageHeader } from "@infinity-radius/ui";
import type { StatusVariant } from "@infinity-radius/ui";
import { apiMutate, ApiClientError } from "@/lib/api-client";
import { useAccessToken } from "@/lib/hooks/use-access-token";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface WithdrawalRow {
  id: string;
  tenant_id: string;
  amount: string;
  currency: string;
  destination_id: string;
  status: string;
  verified_recipient_name: string | null;
  // Never the OTP itself — only whether it was verified. See
  // app/schemas/finance.py's WithdrawalRead.
  two_factor_confirmed_at: string | null;
  created_at: string;
}

interface ReconciliationHealth {
  last_run_at: string | null;
  minutes_since_last_run: number | null;
  currently_processing: number;
  currently_ambiguous: number;
}

const STATUS_VARIANTS: Record<string, StatusVariant> = {
  DRAFT: "neutral",
  PENDING_APPROVAL: "pending",
  APPROVED: "pending",
  PROCESSING: "warning",
  AMBIGUOUS: "danger",
  SUCCESS: "success",
  FAILED: "danger",
  REJECTED: "neutral",
  CANCELLED: "neutral",
  REVERSED: "neutral",
};

// The "Pending Approval" tab hits the narrower, purpose-built approval
// queue endpoint (GET /admin/withdrawals) so approve/reject stay exactly
// as they were; every other tab hits the broader GET /admin/withdrawals/all
// with a status filter — see app/api/v1/admin_withdrawals.py.
const TABS = [
  { key: "PENDING_APPROVAL", label: "Pending Approval" },
  { key: "PROCESSING", label: "Processing" },
  { key: "AMBIGUOUS", label: "Ambiguous" },
  { key: "SUCCESS", label: "Completed" },
  { key: "FAILED", label: "Failed" },
  { key: "REJECTED", label: "Rejected" },
  { key: "ALL", label: "All" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function DisbursementsPage() {
  const { token } = useAccessToken();
  const [tab, setTab] = useState<TabKey>("PENDING_APPROVAL");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const queuePath =
    tab === "PENDING_APPROVAL"
      ? "/api/v1/admin/withdrawals"
      : tab === "ALL"
        ? "/api/v1/admin/withdrawals/all?page_size=50"
        : `/api/v1/admin/withdrawals/all?status=${tab}&page_size=50`;
  const queue = useApiQuery<{ data: WithdrawalRow[] }>(queuePath);
  const health = useApiQuery<{ data: ReconciliationHealth }>(
    "/api/v1/super-admin/reconciliation-health",
  );

  async function approve(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await apiMutate(`/api/v1/admin/withdrawals/${id}/approve`, { accessToken: token, body: {} });
      queue.refetch();
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Could not approve withdrawal");
    } finally {
      setBusyId(null);
    }
  }

  async function reject(id: string) {
    if (!reason.trim()) return;
    setBusyId(id);
    setError(null);
    try {
      await apiMutate(`/api/v1/admin/withdrawals/${id}/reject`, {
        accessToken: token,
        body: { reason },
      });
      setRejectingId(null);
      setReason("");
      queue.refetch();
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Could not reject withdrawal");
    } finally {
      setBusyId(null);
    }
  }

  async function requery(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await apiMutate(`/api/v1/admin/withdrawals/${id}/requery`, { accessToken: token, body: {} });
      queue.refetch();
      health.refetch();
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Could not re-query provider");
    } finally {
      setBusyId(null);
    }
  }

  const rows = queue.data?.data ?? [];
  const healthData = health.data?.data;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Disbursements"
        description="Tenant withdrawals across every status — approval, processing, and reconciliation."
      />

      {healthData && (
        <div className="bg-surface-container-low border-outline-variant/40 flex flex-wrap items-center gap-4 rounded-xl border p-4 text-sm">
          <StatusBadge
            variant={
              healthData.minutes_since_last_run !== null && healthData.minutes_since_last_run < 5
                ? "online"
                : "offline"
            }
            label={
              healthData.minutes_since_last_run !== null
                ? `Reconciliation last ran ${Math.round(healthData.minutes_since_last_run)}m ago`
                : "Reconciliation never run"
            }
            pulse
          />
          <span className="text-on-surface-variant">
            Currently processing: <strong>{healthData.currently_processing}</strong>
          </span>
          <span className="text-on-surface-variant">
            Currently ambiguous: <strong>{healthData.currently_ambiguous}</strong>
          </span>
        </div>
      )}

      {error && (
        <p className="bg-danger/10 text-danger rounded-lg px-3 py-2 text-sm">{error}</p>
      )}

      <div className="flex flex-wrap gap-2 border-b border-outline-variant/40 pb-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={
              tab === t.key
                ? "bg-primary-container text-on-primary-container rounded-lg px-3 py-1.5 text-sm font-semibold"
                : "text-on-surface-variant hover:text-on-surface rounded-lg px-3 py-1.5 text-sm"
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      <DataTable<WithdrawalRow>
        columns={[
          { key: "tenant_id", header: "Tenant" },
          {
            key: "amount",
            header: "Amount",
            align: "right",
            render: (row) => <MoneyDisplay amount={row.amount} currency={row.currency} />,
          },
          {
            key: "verified_recipient_name",
            header: "Recipient",
            render: (row) => row.verified_recipient_name ?? "Not yet verified",
          },
          {
            key: "two_factor_confirmed_at",
            header: "2FA Verified",
            render: (row) => (row.two_factor_confirmed_at ? "Yes" : "No"),
          },
          {
            key: "created_at",
            header: "Requested",
            render: (row) => new Date(row.created_at).toLocaleString(),
          },
          {
            key: "status",
            header: "Status",
            align: "right",
            render: (row) => (
              <StatusBadge
                variant={STATUS_VARIANTS[row.status] ?? "neutral"}
                label={row.status.replace(/_/g, " ")}
              />
            ),
          },
          {
            key: "actions",
            header: "",
            align: "right",
            render: (row) => {
              if (row.status === "PENDING_APPROVAL") {
                return rejectingId === row.id ? (
                  <div className="flex items-center justify-end gap-2">
                    <input
                      autoFocus
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Rejection reason"
                      className="bg-surface-container-high text-on-surface rounded-lg px-2 py-1 text-xs"
                    />
                    <button
                      type="button"
                      disabled={busyId === row.id || !reason.trim()}
                      onClick={() => reject(row.id)}
                      className="bg-danger/15 text-danger rounded-lg px-3 py-1 text-xs font-semibold disabled:opacity-50"
                    >
                      Confirm
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRejectingId(null);
                        setReason("");
                      }}
                      className="text-on-surface-variant text-xs"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      disabled={busyId === row.id}
                      onClick={() => approve(row.id)}
                      className="bg-primary-container text-on-primary-container rounded-lg px-3 py-1 text-xs font-semibold disabled:opacity-50"
                    >
                      {busyId === row.id ? "Working…" : "Approve"}
                    </button>
                    <button
                      type="button"
                      disabled={busyId === row.id}
                      onClick={() => setRejectingId(row.id)}
                      className="bg-danger/15 text-danger rounded-lg px-3 py-1 text-xs font-semibold disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                );
              }
              // PROCESSING/AMBIGUOUS: the ONLY safe manual action is a
              // re-query (authenticated transaction/query) — never a
              // resubmit/resend. See app/api/v1/admin_withdrawals.py.
              if (row.status === "PROCESSING" || row.status === "AMBIGUOUS") {
                return (
                  <button
                    type="button"
                    disabled={busyId === row.id}
                    onClick={() => requery(row.id)}
                    className="bg-surface-container-high text-on-surface rounded-lg px-3 py-1 text-xs font-semibold disabled:opacity-50"
                  >
                    {busyId === row.id ? "Querying…" : "Re-query Provider"}
                  </button>
                );
              }
              return null;
            },
          },
        ]}
        rows={rows}
        state={
          queue.state === "loading" ? "loading" : queue.state === "error" ? "error" : rows.length === 0 ? "empty" : "success"
        }
        emptyState={{
          icon: <Send size={28} />,
          title: "No withdrawals in this view",
          description: "Withdrawals matching this status will appear here.",
        }}
      />
    </div>
  );
}
