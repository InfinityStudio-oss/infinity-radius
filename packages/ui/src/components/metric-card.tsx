import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export type MetricStatus = "ok" | "no_data" | "not_configured" | "unavailable";

const STATUS_CAPTION: Record<Exclude<MetricStatus, "ok">, string> = {
  no_data: "No data",
  not_configured: "Not configured",
  unavailable: "Unavailable",
};

export type MetricAccent = "primary" | "secondary" | "tertiary" | "success" | "warning" | "danger";

const ACCENT_LINE: Record<MetricAccent, string> = {
  primary: "via-primary",
  secondary: "via-secondary",
  tertiary: "via-tertiary",
  success: "via-success",
  warning: "via-warning",
  danger: "via-danger",
};

const ACCENT_ICON: Record<MetricAccent, string> = {
  primary: "bg-primary/10 text-primary",
  secondary: "bg-secondary/10 text-secondary",
  tertiary: "bg-tertiary/10 text-tertiary",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-danger/10 text-danger",
};

const ACCENT_BAR: Record<MetricAccent, string> = {
  primary: "bg-primary",
  secondary: "bg-secondary",
  tertiary: "bg-tertiary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

export interface MetricCardProps {
  label: string;
  /** Pre-formatted display value (e.g. via MoneyDisplay logic upstream) — only rendered when status is "ok". */
  value?: string | number;
  /** Small trailing caption under the value, e.g. a real trend or breakdown. Only shown when status is "ok". */
  caption?: ReactNode;
  status?: MetricStatus;
  icon?: ReactNode;
  accent?: MetricAccent;
  /** A real 0-1 fraction (e.g. routers_online / routers_total) to render as
   * a thin fill bar under the value — omit entirely rather than pass an
   * invented number; the bar only ever appears when this is provided. */
  progress?: number;
  className?: string;
  /** Tighter padding/font sizes for a dense grid (e.g. many KPI cards on
   * one screen) — default false leaves every existing consumer unchanged. */
  compact?: boolean;
}

/**
 * KPI tile for dashboard grids. Never renders a fabricated number — when
 * `status` isn't "ok" it shows an honest caption ("No data" / "Not
 * configured" / "Unavailable") in place of the value, and the bottom
 * progress bar only renders when a real `progress` fraction is supplied.
 */
export function MetricCard({
  label,
  value,
  caption,
  status = "ok",
  icon,
  accent = "primary",
  progress,
  className,
  compact = false,
}: MetricCardProps) {
  const isOk = status === "ok";

  return (
    <div
      className={cn(
        "bg-surface-container-low/90 border-outline-variant/40 hover:bg-surface-container hover:border-outline-variant group relative flex flex-col justify-between overflow-hidden rounded-xl border shadow-md backdrop-blur-md transition-all",
        compact ? "p-2.5" : "p-4",
        className,
      )}
    >
      <div
        className={cn(
          "absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent to-transparent opacity-80",
          ACCENT_LINE[accent],
        )}
      />
      <div className="flex items-start justify-between gap-2">
        <span
          className={cn(
            "text-on-surface-variant font-sans font-bold uppercase tracking-wider",
            compact ? "text-[0.625rem]" : "text-[0.6875rem]",
          )}
        >
          {label}
        </span>
        {icon && (
          <span
            className={cn("shrink-0 rounded-lg", compact ? "p-1" : "p-1.5", ACCENT_ICON[accent])}
          >
            {icon}
          </span>
        )}
      </div>

      <div className={compact ? "mt-1" : "mt-2"}>
        {isOk ? (
          <>
            <div className="flex items-baseline gap-1">
              <span
                className={cn(
                  "text-on-surface font-mono font-bold",
                  compact ? "text-lg" : "text-2xl",
                )}
              >
                {value ?? "—"}
              </span>
            </div>
            {caption && (
              <div
                className={cn(
                  "text-on-surface-variant flex items-center gap-1 text-xs",
                  compact ? "mt-0.5" : "mt-1",
                )}
              >
                {caption}
              </div>
            )}
          </>
        ) : (
          <div className="flex items-baseline gap-1">
            <span
              className={cn("text-outline font-mono font-bold", compact ? "text-lg" : "text-2xl")}
            >
              —
            </span>
            <span className="text-on-surface-variant text-xs font-medium">
              {STATUS_CAPTION[status]}
            </span>
          </div>
        )}
      </div>

      {isOk && typeof progress === "number" && (
        <div
          className={cn(
            "bg-surface-container-high h-1 w-full overflow-hidden rounded-full",
            compact ? "mt-2" : "mt-3",
          )}
        >
          <div
            className={cn("h-full rounded-full", ACCENT_BAR[accent])}
            style={{ width: `${Math.round(Math.min(Math.max(progress, 0), 1) * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
