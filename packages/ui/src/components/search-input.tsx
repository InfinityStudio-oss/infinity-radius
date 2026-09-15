import type { InputHTMLAttributes } from "react";
import { cn } from "../lib/cn";

export interface SearchInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  icon?: React.ReactNode;
  containerClassName?: string;
}

/** Icon-prefixed search field used in top bars and filter rows. */
export function SearchInput({ icon, containerClassName, className, ...props }: SearchInputProps) {
  return (
    <div className={cn("relative flex items-center", containerClassName)}>
      <span className="text-on-surface-variant pointer-events-none absolute left-3 flex h-4 w-4 items-center justify-center">
        {icon ?? <DefaultSearchIcon />}
      </span>
      <input
        type="text"
        className={cn(
          "bg-surface-container-lowest text-on-surface placeholder:text-outline focus:ring-primary w-full rounded-lg py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-1",
          className,
        )}
        {...props}
      />
    </div>
  );
}

function DefaultSearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" strokeLinecap="round" />
    </svg>
  );
}
