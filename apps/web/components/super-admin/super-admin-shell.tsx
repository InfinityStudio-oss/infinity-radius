"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { AppShell, Sidebar, TopBar } from "@infinity-radius/ui";
import { PublicLogo } from "@/components/public/public-logo";
import { NotificationsButton } from "@/components/shell/notifications-button";
import { UserFooter } from "@/components/shell/user-footer";
import { SUPER_ADMIN_SECTIONS } from "@/components/super-admin/super-admin-nav";

export function SuperAdminShell({ children }: { children: ReactNode }) {
  return (
    <div className="super-admin-scope">
      <AppShell
        contentClassName="super-admin-light"
        sidebar={
          <Sidebar
            brand={
              <Link href="/" className="flex items-center" aria-label="Return to the Infinity Radius website">
                <PublicLogo variant="full" priority className="h-11" />
              </Link>
            }
            sections={SUPER_ADMIN_SECTIONS}
            footer={<UserFooter />}
          />
        }
        topBar={(mobileMenuButton) => (
          <TopBar
            mobileMenuButton={mobileMenuButton}
            className="bg-white/95 shadow-[0_1px_8px_rgba(16,20,40,0.06)]"
            title="Platform Super Admin"
            actions={<NotificationsButton />}
          />
        )}
      >
        {children}
      </AppShell>
    </div>
  );
}
