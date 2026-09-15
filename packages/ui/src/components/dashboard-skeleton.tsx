import { cn } from "../lib/cn";
import { LoadingSkeleton, LoadingSkeletonCard } from "./loading-skeleton";

export interface DashboardSkeletonProps {
  className?: string;
}

/** Metric-card row placeholder — pass the real card count so the grid
 * doesn't visually jump once data arrives. */
export function DashboardMetricGridSkeleton({
  count = 6,
  className,
}: DashboardSkeletonProps & { count?: number }) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6",
        className,
      )}
    >
      {Array.from({ length: count }).map((_, i) => (
        <LoadingSkeletonCard key={i} />
      ))}
    </div>
  );
}

/** Chart-panel placeholder — a fixed-height shimmering block matching
 * where the real chart/EmptyChartState will render. `heightClassName` is a
 * Tailwind height utility (e.g. "h-60" for the default 240px chart height,
 * matching EmptyChartState's default). */
export function DashboardChartSkeleton({
  heightClassName = "h-60",
  className,
}: DashboardSkeletonProps & { heightClassName?: string }) {
  return <LoadingSkeleton className={cn("w-full", heightClassName, className)} />;
}

/** Row-list placeholder for router-health/transaction/session panels. */
export function DashboardListSkeleton({
  rows = 4,
  className,
}: DashboardSkeletonProps & { rows?: number }) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <LoadingSkeleton key={i} className="h-14 w-full rounded-lg" />
      ))}
    </div>
  );
}
