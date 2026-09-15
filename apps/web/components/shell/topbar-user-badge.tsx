"use client";

import { ChevronDown } from "lucide-react";
import { useCurrentUser } from "@/lib/hooks/use-current-user";

/**
 * Compact avatar + dropdown chevron in the top bar's right side — real,
 * database-resolved identity (see useCurrentUser), never a placeholder
 * name. Name/role are already shown in full in the sidebar footer
 * (UserFooter), so this stays deliberately compact rather than repeating
 * them a second time.
 */
export function TopBarUserBadge() {
  const { state, data } = useCurrentUser();

  if (state !== "success" || !data) {
    return <div className="bg-surface-container-high h-9 w-9 animate-pulse rounded-full" />;
  }

  const displayName = data.data.full_name ?? data.data.email ?? "Account";
  const initial = displayName.slice(0, 1).toUpperCase();

  return (
    <button
      type="button"
      aria-label={`Account: ${displayName}`}
      className="hover:bg-surface-container-high flex items-center gap-1 rounded-full p-0.5 pr-1.5 transition-colors"
    >
      <div className="bg-primary text-on-primary flex h-8 w-8 shrink-0 items-center justify-center rounded-full">
        <span className="text-sm font-bold">{initial}</span>
      </div>
      <ChevronDown size={14} className="text-on-surface-variant hidden sm:block" />
    </button>
  );
}
