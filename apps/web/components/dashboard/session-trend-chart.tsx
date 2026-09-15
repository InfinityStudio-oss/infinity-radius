"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DashboardChartSkeleton, EmptyChartState, ErrorState } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface SessionTrendPoint {
  date: string;
  session_count: number;
}

interface SessionTrendResponse {
  success: boolean;
  data: SessionTrendPoint[];
}

function SessionTooltip({
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
      <p className="text-on-surface font-mono font-semibold">{point.value} sessions</p>
    </div>
  );
}

/** Real sessions-started-per-day for the trailing window — see
 * GET /api/v1/dashboard/session-trend. Empty until the RADIUS accounting
 * integration writes real user_sessions rows; renders EmptyChartState
 * rather than a fabricated bar series in the meantime. */
export function SessionTrendChart() {
  const { state, data, error, refetch } =
    useApiQuery<SessionTrendResponse>("/api/v1/dashboard/session-trend");

  if (state === "loading") return <DashboardChartSkeleton />;

  if (state === "error" || !data) {
    return (
      <ErrorState
        title="Unable to load session activity"
        description={error?.message}
        onRetry={refetch}
        className="h-60"
      />
    );
  }

  const points = data.data;
  if (points.length === 0) {
    return <EmptyChartState title="No activity recorded yet" />;
  }

  const chartData = points.map((point) => ({ date: point.date.slice(5), count: point.session_count }));

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
        <Tooltip content={<SessionTooltip />} cursor={{ fill: "var(--color-surface-container-high)" }} />
        <Bar dataKey="count" fill="var(--color-secondary)" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
