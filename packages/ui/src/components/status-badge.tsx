import { cn } from "../lib/cn";

export type StatusVariant =
  "online" | "offline" | "degraded" | "pending" | "success" | "warning" | "danger" | "neutral";

const VARIANT_STYLES: Record<StatusVariant, { dot: string; text: string; bg: string }> = {
  online: { dot: "bg-secondary", text: "text-secondary", bg: "bg-secondary/10" },
  success: { dot: "bg-success", text: "text-success", bg: "bg-success/10" },
  offline: { dot: "bg-danger", text: "text-danger", bg: "bg-danger/10" },
  danger: { dot: "bg-danger", text: "text-danger", bg: "bg-danger/10" },
  degraded: { dot: "bg-warning", text: "text-warning", bg: "bg-warning/10" },
  pending: { dot: "bg-warning", text: "text-warning", bg: "bg-warning/10" },
  warning: { dot: "bg-warning", text: "text-warning", bg: "bg-warning/10" },
  neutral: { dot: "bg-outline", text: "text-on-surface-variant", bg: "bg-surface-container-high" },
};

export interface StatusBadgeProps {
  variant: StatusVariant;
  label: string;
  pulse?: boolean;
  className?: string;
}

/** Small dot + label pill used throughout dashboards for live/operational state. */
export function StatusBadge({ variant, label, pulse = false, className }: StatusBadgeProps) {
  const styles = VARIANT_STYLES[variant];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[0.6875rem] font-semibold tracking-wide",
        styles.bg,
        styles.text,
        className,
      )}
    >
      <span className="relative flex h-1.5 w-1.5">
        {pulse && (
          <span
            className={cn(
              "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
              styles.dot,
            )}
          />
        )}
        <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", styles.dot)} />
      </span>
      {label}
    </span>
  );
}
