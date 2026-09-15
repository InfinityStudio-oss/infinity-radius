"use client";

import { useState } from "react";
import { SegmentedTabs } from "@infinity-radius/ui";
import { CollectionsTrendChart } from "@/components/dashboard/collections-trend-chart";
import { SessionTrendChart } from "@/components/dashboard/session-trend-chart";

const TABS = [
  { value: "collections", label: "Collections" },
  { value: "sessions", label: "Sessions" },
] as const;

/**
 * A single chart area with a segmented tab switcher, matching the
 * screenshot's compact-tabs treatment — switching between the two real
 * trend datasets this backend actually has
 * (GET /api/v1/dashboard/collections-trend and .../session-trend). No
 * "Bandwidth"/"Voucher Sales" tab is offered: there is no real dataset
 * behind either yet, and this never fabricates one just to fill a tab.
 */
export function CollectionsUsagePanel() {
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("collections");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-on-surface-variant text-xs font-semibold uppercase tracking-wide">
          {tab === "collections" ? "Gross collections, last 14 days" : "Sessions started, last 14 days"}
        </span>
        <SegmentedTabs options={[...TABS]} value={tab} onChange={(v) => setTab(v as typeof tab)} />
      </div>
      {tab === "collections" ? <CollectionsTrendChart /> : <SessionTrendChart />}
    </div>
  );
}
