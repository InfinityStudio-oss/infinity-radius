import { cn } from "../lib/cn";

export interface SegmentedTabOption {
  value: string;
  label: string;
}

export interface SegmentedTabsProps {
  options: SegmentedTabOption[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

/** Compact pill-group tab switcher — e.g. for choosing which real dataset
 * a chart panel currently plots. Never renders a tab whose data isn't real. */
export function SegmentedTabs({ options, value, onChange, className }: SegmentedTabsProps) {
  return (
    <div
      className={cn(
        "bg-surface-container-high inline-flex items-center gap-0.5 rounded-lg p-0.5",
        className,
      )}
      role="tablist"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
              active
                ? "bg-primary-container text-on-primary-container"
                : "text-on-surface-variant hover:text-on-surface",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
