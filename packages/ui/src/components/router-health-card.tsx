import { cn } from "../lib/cn";
import { RouterStatusIndicator, type RouterStatus } from "./router-status-indicator";

export interface RouterHealthStat {
  label: string;
  /** Pre-formatted display value, or null/undefined when this signal has
   * no real source yet — renders "Unavailable", never a guessed number. */
  value: string | number | null | undefined;
}

export interface RouterHealthCardProps {
  name: string;
  status: RouterStatus;
  /** e.g. Active Users / Latency / CPU Load / Uptime / Last Seen. */
  stats: RouterHealthStat[];
  className?: string;
}

/** One router/NAS gateway's health row for the Network Health panel. */
export function RouterHealthCard({ name, status, stats, className }: RouterHealthCardProps) {
  return (
    <div
      className={cn(
        "bg-surface-container flex flex-col gap-2.5 rounded-lg p-3",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-on-surface truncate text-sm font-semibold">{name}</span>
        <RouterStatusIndicator status={status} />
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3">
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col">
            <dt className="text-on-surface-variant text-[0.6875rem] uppercase tracking-wide">
              {stat.label}
            </dt>
            <dd
              className={cn(
                "font-mono text-xs font-semibold",
                stat.value === null || stat.value === undefined
                  ? "text-outline"
                  : "text-on-surface",
              )}
            >
              {stat.value ?? "Unavailable"}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
