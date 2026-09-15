"use client";

import { useState } from "react";
import { SegmentedTabs } from "@infinity-radius/ui";
import { CollectionsTrendChart } from "@/components/dashboard/collections-trend-chart";
import { TenantGrowthChart } from "@/components/super-admin/tenant-growth-chart";

const TABS = [
  { value: "collections", label: "Collections" },
  { value: "growth", label: "Tenant Growth" },
] as const;

/**
 * A single chart area with a segmented tab switcher — the two real
 * platform-wide trend datasets this backend actually has
 * (GET /api/v1/super-admin/collections-trend and .../tenant-growth-trend).
 * No other tab is offered: there is no real dataset behind a generic
 * "platform growth" chart beyond these two, and this never fabricates one.
 */
export function PlatformTrendsPanel() {
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("collections");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-on-surface-variant text-xs font-semibold uppercase tracking-wide">
          {tab === "collections"
            ? "Gross collections across all tenants, last 14 days"
            : "New tenants onboarded, last 30 days"}
        </span>
        <SegmentedTabs options={[...TABS]} value={tab} onChange={(v) => setTab(v as typeof tab)} />
      </div>
      {tab === "collections" ? (
        <CollectionsTrendChart path="/api/v1/super-admin/collections-trend" />
      ) : (
        <TenantGrowthChart />
      )}
    </div>
  );
}
