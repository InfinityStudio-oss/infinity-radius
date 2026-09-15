import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface TopBarProps {
  title: ReactNode;
  subtitle?: ReactNode;
  search?: ReactNode;
  actions?: ReactNode;
  /** Rendered on small screens to open the mobile sidebar drawer. */
  mobileMenuButton?: ReactNode;
  className?: string;
}

/** Fixed top bar rendered beside the Sidebar (offset via sidebarOffsetClassName on the wrapper). */
export function TopBar({
  title,
  subtitle,
  search,
  actions,
  mobileMenuButton,
  className,
}: TopBarProps) {
  return (
    <header
      className={cn(
        // `left-0 lg:left-72` gives this fixed header an explicit width
        // bounded by the sidebar (w-72) on desktop, instead of relying on
        // `right-0` alone with an auto/shrink-to-fit width — which could
        // otherwise render title/content starting underneath the sidebar.
        "bg-surface-container/80 fixed left-0 right-0 top-0 z-40 flex h-20 items-center justify-between gap-4 px-4 shadow-[0_1px_8px_rgba(0,0,0,0.2)] backdrop-blur-xl sm:px-6 lg:left-72",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-4">
        {mobileMenuButton}
        <div className="flex min-w-0 flex-col">
          <span className="text-on-surface truncate text-lg font-semibold leading-tight">
            {title}
          </span>
          {subtitle && <div className="mt-0.5 flex items-center gap-1.5">{subtitle}</div>}
        </div>
        {search && <div className="hidden lg:block">{search}</div>}
      </div>

      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </header>
  );
}
