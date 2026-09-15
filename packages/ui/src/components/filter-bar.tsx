import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface FilterBarProps {
  children: ReactNode;
  className?: string;
}

/** Horizontal, wrapping row for a SearchInput plus filter controls/pills above a DataTable. */
export function FilterBar({ children, className }: FilterBarProps) {
  return (
    <div
      className={cn(
        "bg-surface-container-low flex flex-wrap items-center gap-2 rounded-xl p-2",
        className,
      )}
    >
      {children}
    </div>
  );
}

export interface FilterPillProps {
  active?: boolean;
  onClick?: () => void;
  children: ReactNode;
}

/** A single selectable pill inside a FilterBar (e.g. "All", "Active", "Failed"). */
export function FilterPill({ active = false, onClick, children }: FilterPillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1 font-mono text-[0.6875rem] font-semibold transition-colors",
        active
          ? "bg-primary-container text-on-primary-container"
          : "bg-surface-container text-on-surface-variant hover:text-on-surface",
      )}
    >
      {children}
    </button>
  );
}
