"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DashboardChartSkeleton, EmptyChartState, ErrorState } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface TenantGrowthPoint {
  date: string;
  new_tenants: number;
}

interface TenantGrowthResponse {
  success: boolean;
  data: TenantGrowthPoint[];
}

function GrowthTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) {
  const point = payload?.[0];
  if (!active || !point) return null;
  return (
    <div className="bg-surface-container-high border-outline-variant rounded-lg border px-3 py-2 text-xs shadow-lg">
      <p className="text-on-surface-variant">{label}</p>
      <p className="text-on-surface font-mono font-semibold">
        {point.value} new tenant{point.value === 1 ? "" : "s"}
      </p>
    </div>
  );
}

/** Real new-tenants-per-day across the platform for the trailing 30 days —
 * see GET /api/v1/super-admin/tenant-growth-trend. Never draws a
 * fabricated growth curve; an empty series renders EmptyChartState. */
export function TenantGrowthChart() {
  const { state, data, error, refetch } = useApiQuery<TenantGrowthResponse>(
    "/api/v1/super-admin/tenant-growth-trend",
  );

  if (state === "loading") return <DashboardChartSkeleton />;

  if (state === "error" || !data) {
    return (
      <ErrorState
        title="Unable to load tenant growth"
        description={error?.message}
        onRetry={refetch}
        className="h-60"
      />
    );
  }

  const points = data.data;
  if (points.length === 0) {
    return (
      <EmptyChartState
        title="No tenant growth recorded yet"
        description="New tenant sign-ups will appear here as they onboard."
      />
    );
  }

  const chartData = points.map((point) => ({ date: point.date.slice(5), count: point.new_tenants }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-outline-variant)" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: "var(--color-on-surface-variant)", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "var(--color-outline-variant)" }}
        />
        <YAxis
          tick={{ fill: "var(--color-on-surface-variant)", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={28}
          allowDecimals={false}
        />
        <Tooltip content={<GrowthTooltip />} cursor={{ fill: "var(--color-surface-container-high)" }} />
        <Bar dataKey="count" fill="var(--color-tertiary)" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
