import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface DashboardSectionProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Titled content panel used for every dashboard chart/table/list section
 * — the one visual container every "card" of the dashboard shares. */
export function DashboardSection({
  title,
  description,
  actions,
  children,
  className,
}: DashboardSectionProps) {
  return (
    <section
      className={cn(
        "bg-surface-container-low border-outline-variant/40 flex flex-col rounded-xl border p-4",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-on-surface text-base font-semibold sm:text-lg">{title}</h2>
          {description && <p className="text-on-surface-variant mt-1 text-sm">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      <div className="mt-4 flex-1">{children}</div>
    </section>
  );
}
