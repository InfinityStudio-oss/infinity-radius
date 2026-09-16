"use client";

import { useState } from "react";
import { Wallet as WalletIcon, ArrowUpFromLine } from "lucide-react";
import {
  MetricCard,
  MoneyDisplay,
  PageHeader,
  StatusBadge,
  DataTable,
  formatMoney,
} from "@infinity-radius/ui";
import type { StatusVariant } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";
import { WithdrawDialog } from "@/components/dashboard/withdraw-dialog";

interface Wallet {
  available_balance_tzs: string;
  pending_balance_tzs: string;
  reserved_balance_tzs: string;
  total_disbursed_tzs: string;
}

interface Destination {
  id: string;
  label: string;
  channel: string;
  destination_code: string | null;
  account_number: string | null;
  account_name: string | null;
  is_default: boolean;
}

interface Withdrawal {
  id: string;
  amount: string;
  currency: string;
  status: string;
  approval_required: boolean;
  created_at: string;
}

const STATUS_VARIANT: Record<string, StatusVariant> = {
  DRAFT: "neutral",
  PENDING_APPROVAL: "pending",
  APPROVED: "pending",
  PROCESSING: "pending",
  AMBIGUOUS: "warning",
  SUCCESS: "success",
  FAILED: "danger",
  REJECTED: "danger",
  CANCELLED: "neutral",
  REVERSED: "warning",
};

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Awaiting confirmation",
  PENDING_APPROVAL: "Awaiting approval",
  APPROVED: "Approved",
  PROCESSING: "Processing",
  AMBIGUOUS: "Under review",
  SUCCESS: "Completed",
  FAILED: "Failed",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
  REVERSED: "Reversed",
};

export default function WalletPage() {
  const wallet = useApiQuery<{ data: Wallet }>("/api/v1/wallet");
  const destinations = useApiQuery<{ data: Destination[] }>("/api/v1/payouts/destinations");
  const withdrawals = useApiQuery<{ data: Withdrawal[] }>("/api/v1/payouts");
  const [dialogOpen, setDialogOpen] = useState(false);

  const balance = wallet.data?.data;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Wallet"
        description="Your settlement balance and withdrawal history."
        actions={
          <button
            type="button"
            onClick={() => setDialogOpen(true)}
            disabled={wallet.state !== "success"}
            className="bg-primary-container text-on-primary-container flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            <ArrowUpFromLine size={16} />
            Withdraw
          </button>
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MetricCard
          label="Available Balance"
          icon={<WalletIcon size={18} />}
          accent="primary"
          status={balance ? "ok" : wallet.state === "loading" ? "no_data" : "unavailable"}
          value={formatMoney(balance?.available_balance_tzs, "TZS") ?? undefined}
        />
        <MetricCard
          label="Reserved (pending withdrawals)"
          accent="secondary"
          status={balance ? "ok" : wallet.state === "loading" ? "no_data" : "unavailable"}
          value={formatMoney(balance?.reserved_balance_tzs, "TZS") ?? undefined}
        />
        <MetricCard
          label="Total Disbursed"
          accent="tertiary"
          status={balance ? "ok" : wallet.state === "loading" ? "no_data" : "unavailable"}
          value={formatMoney(balance?.total_disbursed_tzs, "TZS") ?? undefined}
        />
      </div>

      <DataTable<Withdrawal>
        columns={[
          {
            key: "created_at",
            header: "Requested",
            render: (row) => new Date(row.created_at).toLocaleString(),
          },
          {
            key: "amount",
            header: "Amount",
            align: "right",
            render: (row) => <MoneyDisplay amount={row.amount} currency={row.currency} />,
          },
          {
            key: "status",
            header: "Status",
            align: "right",
            render: (row) => (
              <StatusBadge
                variant={STATUS_VARIANT[row.status] ?? "neutral"}
                label={STATUS_LABEL[row.status] ?? row.status}
              />
            ),
          },
        ]}
        rows={withdrawals.data?.data ?? []}
        state={
          withdrawals.state === "loading"
            ? "loading"
            : withdrawals.state === "error"
              ? "error"
              : (withdrawals.data?.data.length ?? 0) === 0
                ? "empty"
                : "success"
        }
        emptyState={{
          icon: <WalletIcon size={28} />,
          title: "No withdrawals yet",
          description: "Withdrawals you request will appear here with live status.",
        }}
      />

      <WithdrawDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        destinations={destinations.data?.data ?? []}
        onCompleted={() => {
          wallet.refetch();
          withdrawals.refetch();
        }}
      />
    </div>
  );
}
