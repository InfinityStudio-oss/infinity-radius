"use client";

import { Coins, Router, ShieldAlert, Ticket, Wallet, Wifi } from "lucide-react";
import { DashboardMetricCard, DashboardMetricGridSkeleton, ErrorState } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

export interface DashboardSummary {
  online_users: number;
  today_collections_tzs: string;
  active_vouchers: number;
  routers_online: number;
  routers_total: number;
  failed_transactions: number;
  available_wallet_balance_tzs: string;
}

interface DashboardSummaryResponse {
  success: boolean;
  data: DashboardSummary;
}

/** The 6 real, tenant-scoped KPI cards — see GET /api/v1/dashboard/summary.
 * Every value is a real COUNT()/SUM() against this tenant's own rows;
 * 0 is a legitimate, honestly-rendered answer on an empty tenant. */
export function DashboardSummaryCards() {
  const { state, data, error, refetch } =
    useApiQuery<DashboardSummaryResponse>("/api/v1/dashboard/summary");

  if (state === "loading") return <DashboardMetricGridSkeleton count={6} />;

  if (state === "error" || !data) {
    return (
      <ErrorState
        title="Unable to load dashboard metrics"
        description={error?.message}
        onRetry={refetch}
      />
    );
  }

  const summary = data.data;
  const cardClassName = "shadow-sm hover:shadow-md";

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
      <DashboardMetricCard
        label="Online Users"
        icon={<Wifi size={14} />}
        accent="secondary"
        status="ok"
        value={summary.online_users}
        caption="Active sessions now"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Today's Collections"
        icon={<Coins size={14} />}
        accent="primary"
        status="ok"
        format="money"
        value={summary.today_collections_tzs}
        caption="Since midnight, Dar es Salaam time"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Active Vouchers"
        icon={<Ticket size={14} />}
        accent="tertiary"
        status="ok"
        value={summary.active_vouchers}
        caption="Unused & redeemable"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Routers Online"
        icon={<Router size={14} />}
        accent="secondary"
        status="ok"
        format="raw"
        value={`${summary.routers_online} / ${summary.routers_total}`}
        caption="Of routers configured"
        progress={summary.routers_total > 0 ? summary.routers_online / summary.routers_total : 0}
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Failed Transactions"
        icon={<ShieldAlert size={14} />}
        accent="danger"
        status="ok"
        value={summary.failed_transactions}
        caption="Today"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Available Wallet Balance"
        icon={<Wallet size={14} />}
        accent="primary"
        status="ok"
        format="money"
        value={summary.available_wallet_balance_tzs}
        caption="Withdrawable now"
        className={cardClassName}
        compact
      />
    </div>
  );
}
