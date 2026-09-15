import { DashboardSection, PageHeader } from "@infinity-radius/ui";
import { CollectionsUsagePanel } from "@/components/dashboard/collections-usage-panel";
import { DashboardHeaderActions } from "@/components/dashboard/dashboard-header-actions";
import { DashboardSummaryCards } from "@/components/dashboard/dashboard-summary-cards";
import { NetworkHealthPanel } from "@/components/dashboard/network-health-panel";
import { PackagePerformancePanel } from "@/components/dashboard/package-performance-panel";
import { RecentSessionsTable } from "@/components/dashboard/recent-sessions-table";
import { RecentTransactionsTable } from "@/components/dashboard/recent-transactions-table";

export default function DashboardOverviewPage() {
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        size="large"
        title="Hotspot Operations Command Center"
        description="Real-time visibility into routers, sessions, billing, and settlements across your network."
        actions={<DashboardHeaderActions />}
        titleClassName="lg:text-[42px] lg:leading-[1.08]"
      />

      <DashboardSummaryCards />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <DashboardSection
          title="Collections & Usage Trends"
          className="xl:col-span-2"
        >
          <CollectionsUsagePanel />
        </DashboardSection>

        <DashboardSection
          title="Network Health"
          description="Live MikroTik RouterOS & RADIUS NAS status."
        >
          <NetworkHealthPanel />
        </DashboardSection>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <DashboardSection title="Recent Transactions" className="xl:col-span-2">
          <RecentTransactionsTable />
        </DashboardSection>

        <DashboardSection title="Recent Sessions">
          <RecentSessionsTable />
        </DashboardSection>
      </div>

      <DashboardSection
        title="Package Performance"
        description="Active subscriptions and revenue per package."
      >
        <PackagePerformancePanel />
      </DashboardSection>
    </div>
  );
}
