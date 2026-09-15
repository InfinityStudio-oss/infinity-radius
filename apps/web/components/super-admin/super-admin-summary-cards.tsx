"use client";

import {
  Activity,
  AlertTriangle,
  Banknote,
  Building2,
  Coins,
  Router,
  Scale,
  UserX,
} from "lucide-react";
import {
  DashboardMetricCard,
  DashboardMetricGridSkeleton,
  ErrorState,
  formatMoney,
  type MetricStatus,
} from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface MetricValue {
  status: MetricStatus;
  value: number | string | null;
  caption: string | null;
}

export interface SuperAdminSummary {
  active_tenants: number;
  suspended_tenants: number;
  routers_total: number;
  routers_online: number;
  radius_active_sessions: number;
  collections_today_tzs: string;
  pending_payouts: number;
  pending_payouts_amount_tzs: string;
  failed_webhooks: number;
  reconciliation_exceptions: MetricValue;
}

interface SuperAdminSummaryResponse {
  success: boolean;
  data: SuperAdminSummary;
}

/** The 9 real, platform-wide KPI cards — see
 * GET /api/v1/super-admin/dashboard-summary. Every value is a real
 * COUNT()/SUM() across every tenant; 0 is a legitimate, honestly-rendered
 * answer on a brand-new platform. reconciliation_exceptions has no
 * backing table yet, so it renders "Not configured" rather than a
 * fabricated 0 — see the backend's module docstring. */
export function SuperAdminSummaryCards() {
  const { state, data, error, refetch } = useApiQuery<SuperAdminSummaryResponse>(
    "/api/v1/super-admin/dashboard-summary",
  );

  if (state === "loading") {
    return (
      <DashboardMetricGridSkeleton
        count={9}
        className="grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
      />
    );
  }

  if (state === "error" || !data) {
    return (
      <ErrorState
        title="Unable to load platform metrics"
        description={error?.message}
        onRetry={refetch}
      />
    );
  }

  const summary = data.data;
  const pendingAmount = formatMoney(summary.pending_payouts_amount_tzs);
  const cardClassName = "shadow-sm hover:shadow-md";

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      <DashboardMetricCard
        label="Active Tenants"
        icon={<Building2 size={14} />}
        accent="primary"
        status="ok"
        value={summary.active_tenants}
        caption="Currently active"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Suspended Tenants"
        icon={<UserX size={14} />}
        accent="warning"
        status="ok"
        value={summary.suspended_tenants}
        caption="Currently suspended"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Router Fleet"
        icon={<Router size={14} />}
        accent="tertiary"
        status="ok"
        value={summary.routers_total}
        caption="Provisioned platform-wide"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Online Routers"
        icon={<Router size={14} />}
        accent="secondary"
        status="ok"
        format="raw"
        value={`${summary.routers_online} / ${summary.routers_total}`}
        caption="Of the fleet"
        progress={summary.routers_total > 0 ? summary.routers_online / summary.routers_total : 0}
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="RADIUS Active Sessions"
        icon={<Activity size={14} />}
        accent="secondary"
        status="ok"
        value={summary.radius_active_sessions}
        caption="Online now"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Collections Today"
        icon={<Coins size={14} />}
        accent="primary"
        status="ok"
        format="money"
        value={summary.collections_today_tzs}
        caption="Since midnight, Dar es Salaam time"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Pending Payouts"
        icon={<Banknote size={14} />}
        accent="warning"
        status="ok"
        value={summary.pending_payouts}
        caption={pendingAmount ? `${pendingAmount} awaiting approval` : "Awaiting approval"}
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Failed Webhooks"
        icon={<AlertTriangle size={14} />}
        accent="danger"
        status="ok"
        value={summary.failed_webhooks}
        caption="Verification rejected"
        className={cardClassName}
        compact
      />
      <DashboardMetricCard
        label="Reconciliation Exceptions"
        icon={<Scale size={14} />}
        accent="tertiary"
        status={summary.reconciliation_exceptions.status}
        value={summary.reconciliation_exceptions.value ?? undefined}
        className={cardClassName}
        compact
      />
    </div>
  );
}
