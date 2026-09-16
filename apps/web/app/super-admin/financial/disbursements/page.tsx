"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { MoneyDisplay, DataTable, StatusBadge, PageHeader } from "@infinity-radius/ui";
import { apiMutate, ApiClientError } from "@/lib/api-client";
import { useAccessToken } from "@/lib/hooks/use-access-token";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface PendingWithdrawal {
  id: string;
  tenant_id: string;
  amount: string;
  currency: string;
  destination_id: string;
  verified_recipient_name: string | null;
  created_at: string;
}

export default function DisbursementsPage() {
  const { token } = useAccessToken();
  const queue = useApiQuery<{ data: PendingWithdrawal[] }>("/api/v1/admin/withdrawals");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

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

  const rows = queue.data?.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Disbursements"
        description="Withdrawals above the auto-approval threshold, awaiting Super Admin review."
      />

      {error && (
        <p className="bg-danger/10 text-danger rounded-lg px-3 py-2 text-sm">{error}</p>
      )}

      <DataTable<PendingWithdrawal>
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
            key: "created_at",
            header: "Requested",
            render: (row) => new Date(row.created_at).toLocaleString(),
          },
          {
            key: "id",
            header: "Status",
            align: "right",
            render: () => <StatusBadge variant="pending" label="Pending Approval" />,
          },
          {
            key: "actions",
            header: "",
            align: "right",
            render: (row) =>
              rejectingId === row.id ? (
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
              ),
          },
        ]}
        rows={rows}
        state={
          queue.state === "loading" ? "loading" : queue.state === "error" ? "error" : rows.length === 0 ? "empty" : "success"
        }
        emptyState={{
          icon: <Send size={28} />,
          title: "No withdrawals awaiting approval",
          description: "Withdrawals over the auto-approval threshold will appear here.",
        }}
      />
    </div>
  );
}
