"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { AppShell, Sidebar, TopBar } from "@infinity-radius/ui";
import { PublicLogo } from "@/components/public/public-logo";
import { clientEnv } from "@/lib/env";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useApiQuery } from "@/lib/hooks/use-api-query";
import { NotificationsButton } from "@/components/shell/notifications-button";
import { TopBarUserBadge } from "@/components/shell/topbar-user-badge";
import { UserFooter } from "@/components/shell/user-footer";
import { WalletBalanceChip } from "@/components/shell/wallet-balance-chip";
import {
  DASHBOARD_TOP_ITEMS,
  dashboardSectionsWithRoutersBadge,
} from "@/components/dashboard/dashboard-nav";

const ENV_LABEL: Record<typeof clientEnv.NEXT_PUBLIC_APP_ENV, string> = {
  development: "Development",
  staging: "Staging",
  production: "Production",
};

interface DashboardSummaryResponse {
  success: boolean;
  data: { routers_online: number; routers_total: number };
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const { state, data } = useCurrentUser();
  const tenantName = state === "success" ? (data?.data.tenant_name ?? "Dashboard") : "Dashboard";

  // Powers the Routers nav item's real "online/total" badge (see the
  // screenshot's sidebar) — omitted entirely (not a placeholder badge)
  // until this has actually loaded.
  const { state: summaryState, data: summaryData } =
    useApiQuery<DashboardSummaryResponse>("/api/v1/dashboard/summary");
  const routersBadge =
    summaryState === "success" && summaryData ? (
      <span className="text-secondary bg-secondary/10 rounded-full px-2 py-0.5 font-mono text-[0.625rem] font-semibold">
        {summaryData.data.routers_online}/{summaryData.data.routers_total} Online
      </span>
    ) : undefined;

  return (
    <div className="tenant-scope">
      <AppShell
        contentClassName="tenant-light"
        sidebar={
          <Sidebar
            brand={
              <Link href="/dashboard" className="flex items-center">
                <PublicLogo variant="full" priority className="h-12" />
              </Link>
            }
            topItems={DASHBOARD_TOP_ITEMS}
            sections={dashboardSectionsWithRoutersBadge(routersBadge)}
            footer={<UserFooter />}
          />
        }
        topBar={(mobileMenuButton) => (
          <TopBar
            mobileMenuButton={mobileMenuButton}
            className="bg-white/95 shadow-[0_1px_8px_rgba(16,20,40,0.06)]"
            title={tenantName}
            subtitle={
              <span className="text-secondary inline-flex items-center gap-1.5 font-mono text-[0.6875rem] font-semibold uppercase tracking-wider">
                <span className="bg-secondary h-1.5 w-1.5 rounded-full" />
                {ENV_LABEL[clientEnv.NEXT_PUBLIC_APP_ENV]} environment
              </span>
            }
            actions={
              <>
                <WalletBalanceChip />
                <NotificationsButton />
                <TopBarUserBadge />
              </>
            }
          />
        )}
      >
        {children}
      </AppShell>
    </div>
  );
}
