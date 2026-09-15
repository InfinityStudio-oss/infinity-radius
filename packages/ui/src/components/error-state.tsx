import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface ErrorStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

/**
 * "This is broken/unreachable" panel — distinct from EmptyState ("this is
 * genuinely empty"). Use when a fetch fails or a dependency reports
 * unavailable, never as a stand-in for missing data.
 */
export function ErrorState({
  icon,
  title,
  description,
  onRetry,
  retryLabel = "Retry",
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "border-danger/20 bg-danger/5 flex flex-col items-center justify-center gap-3 rounded-xl border px-6 py-16 text-center",
        className,
      )}
    >
      <div className="text-danger">{icon ?? <DefaultErrorIcon />}</div>
      <p className="text-on-surface text-sm font-semibold">{title}</p>
      {description && <p className="text-on-surface-variant max-w-sm text-sm">{description}</p>}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="bg-surface-container-high text-on-surface hover:bg-surface-variant mt-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors"
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}

function DefaultErrorIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-7 w-7">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5" strokeLinecap="round" />
      <path d="M12 16h.01" strokeLinecap="round" />
    </svg>
  );
}
