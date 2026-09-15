import { cn } from "../lib/cn";

export interface EmptyChartStateProps {
  title: string;
  description?: string;
  className?: string;
  /** Fixed height so the surrounding layout doesn't jump between the empty
   * state and the eventual real chart — match the chart's own height. */
  height?: number;
}

/**
 * Stand-in for a chart with nothing to plot yet. Never draw a fabricated
 * line/bar just to make a panel look populated — render this instead
 * whenever the backing query returns an empty series.
 */
export function EmptyChartState({
  title,
  description,
  className,
  height = 240,
}: EmptyChartStateProps) {
  return (
    <div
      style={{ height }}
      className={cn(
        "border-outline-variant bg-surface-container-low/60 flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed text-center",
        className,
      )}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="text-outline h-8 w-8"
      >
        <path d="M4 19V5M4 19h16M8 19v-6M13 19V9m5 10V6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <p className="text-on-surface text-sm font-semibold">{title}</p>
      {description && <p className="text-on-surface-variant max-w-xs text-xs">{description}</p>}
    </div>
  );
}
