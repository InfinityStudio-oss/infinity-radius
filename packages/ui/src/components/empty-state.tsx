import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

/**
 * Standard "no data yet" panel. Use this instead of seeding fake rows —
 * every list/table/dashboard in Infinity Radius must be able to render
 * this state honestly when the underlying query returns nothing.
 */
export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "border-outline-variant bg-surface-container-low flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-16 text-center",
        className,
      )}
    >
      {icon && <div className="text-outline">{icon}</div>}
      <p className="text-on-surface text-sm font-semibold">{title}</p>
      {description && <p className="text-on-surface-variant max-w-sm text-sm">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
