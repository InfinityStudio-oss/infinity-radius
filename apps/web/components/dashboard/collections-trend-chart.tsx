"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  DashboardChartSkeleton,
  EmptyChartState,
  ErrorState,
  formatMoney,
} from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface CollectionsTrendPoint {
  date: string;
  collections_tzs: string;
}

interface CollectionsTrendResponse {
  success: boolean;
  data: CollectionsTrendPoint[];
}

function TrendTooltip({
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
      <p className="text-on-surface font-mono font-semibold">{formatMoney(point.value) ?? "—"}</p>
    </div>
  );
}

export interface CollectionsTrendChartProps {
  /** Defaults to the tenant-scoped endpoint; the super-admin dashboard
   * passes the platform-wide equivalent (GET /api/v1/super-admin/collections-trend)
   * to reuse this exact rendering rather than duplicating the chart. */
  path?: string;
}

/** Real gross-collections-per-day for the trailing window — see
 * GET /api/v1/dashboard/collections-trend. Never draws a fabricated line;
 * an empty series renders EmptyChartState instead. */
export function CollectionsTrendChart({
  path = "/api/v1/dashboard/collections-trend",
}: CollectionsTrendChartProps) {
  const { state, data, error, refetch } = useApiQuery<CollectionsTrendResponse>(path);

  if (state === "loading") return <DashboardChartSkeleton />;

  if (state === "error" || !data) {
    return (
      <ErrorState
        title="Unable to load collections trend"
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
        title="No collections recorded yet"
        description="Once customers pay for packages, daily totals will appear here."
      />
    );
  }

  const chartData = points.map((point) => ({
    date: point.date.slice(5),
    amount: Number(point.collections_tzs),
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="collectionsFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-primary)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--color-primary)" stopOpacity={0} />
          </linearGradient>
        </defs>
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
          width={40}
          tickFormatter={(value: number) =>
            value >= 1000 ? `${Math.round(value / 1000)}k` : String(value)
          }
        />
        <Tooltip content={<TrendTooltip />} />
        <Area
          type="monotone"
          dataKey="amount"
          stroke="var(--color-primary)"
          strokeWidth={2}
          fill="url(#collectionsFill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
