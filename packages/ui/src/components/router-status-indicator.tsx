import { StatusBadge } from "./status-badge";

export type RouterStatus = "online" | "offline" | "degraded" | "unknown";

const LABELS: Record<RouterStatus, string> = {
  online: "Online",
  offline: "Offline",
  degraded: "Degraded",
  unknown: "Unknown",
};

export interface RouterStatusIndicatorProps {
  status: RouterStatus;
  /** Round-trip latency in ms, when known — omit rather than fabricate. */
  latencyMs?: number;
  className?: string;
}

/** Router/NAS gateway connectivity state, as reported by the Network Agent. */
export function RouterStatusIndicator({
  status,
  latencyMs,
  className,
}: RouterStatusIndicatorProps) {
  const variant =
    status === "online"
      ? "online"
      : status === "degraded"
        ? "degraded"
        : status === "offline"
          ? "offline"
          : "neutral";

  return (
    <span className="inline-flex items-center gap-1.5">
      <StatusBadge
        variant={variant}
        label={LABELS[status]}
        pulse={status === "online"}
        className={className}
      />
      {status === "online" && typeof latencyMs === "number" && (
        <span className="text-on-surface-variant font-mono text-[0.6875rem]">{latencyMs}ms</span>
      )}
    </span>
  );
}
