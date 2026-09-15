"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useCurrentUser } from "@/lib/hooks/use-current-user";

/** Sidebar footer card: real signed-in user name + role (database-resolved,
 * see useCurrentUser — never a hard-coded label) and a working sign-out action. */
export function UserFooter() {
  const router = useRouter();
  const { state, data } = useCurrentUser();

  const displayName = data?.data.full_name ?? data?.data.email ?? null;
  const roleLabel = data?.data.roles[0]?.replaceAll("_", " ") ?? null;

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="flex items-center gap-3">
      <div className="relative flex-shrink-0">
        <div className="bg-primary text-on-primary flex h-8 w-8 items-center justify-center rounded-full">
          <span className="text-xs font-bold uppercase">
            {displayName?.slice(0, 1) ?? "?"}
          </span>
        </div>
        <span className="bg-secondary ring-surface-container-lowest absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-on-surface truncate text-sm font-semibold">
          {state === "loading" ? "Loading…" : (displayName ?? "Unavailable")}
        </span>
        <span className="text-primary truncate text-[0.6875rem] font-semibold uppercase tracking-wide">
          {roleLabel ?? ""}
        </span>
      </div>
      <button
        type="button"
        onClick={handleSignOut}
        aria-label="Sign out"
        className="text-on-surface-variant hover:text-on-surface transition-colors"
      >
        <LogOut size={18} />
      </button>
    </div>
  );
}
