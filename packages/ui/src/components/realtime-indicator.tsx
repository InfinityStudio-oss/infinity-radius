import { cn } from "../lib/cn";

export interface RealtimeIndicatorProps {
  connected: boolean;
  label: string;
  offlineLabel?: string;
  className?: string;
}

/**
 * Live-stream status pill (e.g. "RADIUS Cloud Sync: Live"). Never claims
 * "Live" when the underlying feed is not actually connected — pass
 * `connected` from the real subscription/poll state, not a hardcoded true.
 */
export function RealtimeIndicator({
  connected,
  label,
  offlineLabel = "Offline",
  className,
}: RealtimeIndicatorProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono text-[0.6875rem] font-semibold uppercase tracking-wider",
        connected ? "text-secondary" : "text-outline",
        className,
      )}
    >
      <span className="relative flex h-2 w-2">
        {connected && (
          <span className="bg-secondary absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" />
        )}
        <span
          className={cn(
            "relative inline-flex h-2 w-2 rounded-full",
            connected ? "bg-secondary" : "bg-outline",
          )}
        />
      </span>
      {connected ? label : offlineLabel}
    </span>
  );
}
