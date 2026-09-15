import { DashboardSection, PageHeader } from "@infinity-radius/ui";
import { PendingPayoutsPanel } from "@/components/super-admin/pending-payouts-panel";
import { PlatformActivityPanel } from "@/components/super-admin/platform-activity-panel";
import { PlatformTrendsPanel } from "@/components/super-admin/platform-trends-panel";
import { SuperAdminSummaryCards } from "@/components/super-admin/super-admin-summary-cards";

export default function SuperAdminOverviewPage() {
  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        size="large"
        title="Command Center"
        description="Monitor tenant activity, network infrastructure, RADIUS sessions, collections and settlement operations across the Infinity Radius platform."
        titleClassName="text-[1.5rem] sm:text-[1.875rem] lg:text-[2.25rem] leading-[1.1]"
        descriptionClassName="text-sm sm:text-base max-w-2xl"
      />

      <SuperAdminSummaryCards />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <DashboardSection title="Platform Trends" className="xl:col-span-2">
          <PlatformTrendsPanel />
        </DashboardSection>

        <DashboardSection
          title="Pending Payouts"
          description="Withdrawals awaiting maker-checker approval."
        >
          <PendingPayoutsPanel />
        </DashboardSection>
      </div>

      <DashboardSection
        title="Recent Platform Activity"
        description="Immutable administrative and operational events across every tenant."
      >
        <PlatformActivityPanel />
      </DashboardSection>
    </div>
  );
}
