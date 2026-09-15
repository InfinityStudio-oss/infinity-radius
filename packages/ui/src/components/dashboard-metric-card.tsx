import type { ReactNode } from "react";
import { formatMoney } from "../lib/money";
import { MetricCard, type MetricAccent, type MetricStatus } from "./metric-card";

export interface DashboardMetricCardProps {
  label: string;
  icon?: ReactNode;
  accent?: MetricAccent;
  /** "ok" once a real value has loaded; "unavailable" when the fetch
   * failed. There is no separate loading state here — render
   * DashboardMetricGridSkeleton instead while loading. */
  status: MetricStatus;
  /** "number" formats via Intl.NumberFormat("en-TZ"); "money" formats via
   * the same TZS-coded formatting as MoneyDisplay (e.g. "TZS 1,500"); "raw"
   * displays the string exactly as given (e.g. a "3 / 5" ratio). */
  format?: "number" | "money" | "raw";
  /** Raw value — a plain count for format="number", a decimal string
   * (e.g. "15000.00") for format="money", any pre-formatted string for
   * format="raw". Ignored when status !== "ok". */
  value?: number | string;
  caption?: ReactNode;
  /** A real 0-1 fraction — see MetricCardProps.progress. Never invent one. */
  progress?: number;
  className?: string;
  compact?: boolean;
}

/**
 * One dashboard KPI tile, e.g. "Today's Collections" / "Routers Online".
 * Never renders a fabricated number — status must be driven by the real
 * fetch outcome (see app/dashboard/page.tsx), and a 0 value is rendered
 * as a real "0"/"TZS 0", not mistaken for "no data".
 */
export function DashboardMetricCard({
  label,
  icon,
  accent,
  status,
  format = "number",
  value,
  caption,
  progress,
  className,
  compact,
}: DashboardMetricCardProps) {
  const displayValue =
    status === "ok" && value !== undefined
      ? format === "money"
        ? (formatMoney(value) ?? undefined)
        : format === "raw"
          ? value
          : new Intl.NumberFormat("en-TZ").format(Number(value))
      : undefined;

  return (
    <MetricCard
      label={label}
      icon={icon}
      accent={accent}
      status={status}
      value={displayValue}
      caption={caption}
      progress={progress}
      className={className}
      compact={compact}
    />
  );
}
