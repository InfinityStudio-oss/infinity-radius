import { cn } from "../lib/cn";

export interface LoadingSkeletonProps {
  className?: string;
}

/** A single shimmering bar. Compose these for card/table/text loading states. */
export function LoadingSkeleton({ className }: LoadingSkeletonProps) {
  return <div className={cn("bg-surface-container-high animate-pulse rounded-md", className)} />;
}

export function LoadingSkeletonText({
  lines = 2,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <LoadingSkeleton key={i} className={cn("h-3", i === lines - 1 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}

export function LoadingSkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("bg-surface-container-low flex flex-col gap-3 rounded-xl p-4", className)}>
      <LoadingSkeleton className="h-3 w-1/3" />
      <LoadingSkeleton className="h-7 w-1/2" />
      <LoadingSkeleton className="h-3 w-2/3" />
    </div>
  );
}

export function LoadingSkeletonRow({
  columns = 4,
  className,
}: {
  columns?: number;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-4 px-3 py-3", className)}>
      {Array.from({ length: columns }).map((_, i) => (
        <LoadingSkeleton key={i} className="h-3 flex-1" />
      ))}
    </div>
  );
}
