import {
  LayoutDashboard,
  Radio,
  Router,
  UsersRound,
  Package,
  Ticket,
  Receipt,
  HandCoins,
  Wallet,
  Banknote,
  BarChart3,
  LifeBuoy,
  Settings,
} from "lucide-react";
import type { ReactNode } from "react";
import type { SidebarNavItem, SidebarNavSection } from "@infinity-radius/ui";

export const DASHBOARD_TOP_ITEMS: SidebarNavItem[] = [];

/**
 * Two groups, matching the tenant dashboard's Stitch design source of
 * truth exactly. Every href below is a real, already-implemented route —
 * nothing here is a placeholder link.
 */
export const DASHBOARD_SECTIONS: SidebarNavSection[] = [
  {
    title: "Network Operations",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: <LayoutDashboard />, exact: true },
      { label: "Hotspot Sites", href: "/dashboard/network/hotspot-sites", icon: <Radio /> },
      { label: "Routers", href: "/dashboard/network/routers", icon: <Router /> },
      { label: "RADIUS Users", href: "/dashboard/network/radius-users", icon: <UsersRound /> },
      { label: "Packages", href: "/dashboard/billing/packages", icon: <Package /> },
      { label: "Vouchers", href: "/dashboard/billing/vouchers", icon: <Ticket /> },
    ],
  },
  {
    title: "Finance & Admin",
    items: [
      { label: "Collections", href: "/dashboard/finance/collections", icon: <HandCoins /> },
      { label: "Payments", href: "/dashboard/finance/payments", icon: <Receipt /> },
      { label: "Wallet", href: "/dashboard/finance/wallet", icon: <Wallet /> },
      { label: "Payouts", href: "/dashboard/finance/payouts", icon: <Banknote /> },
      { label: "Reports", href: "/dashboard/management/reports", icon: <BarChart3 /> },
      { label: "Support", href: "/dashboard/management/support", icon: <LifeBuoy /> },
      { label: "Settings", href: "/dashboard/management/settings", icon: <Settings /> },
    ],
  },
];

/**
 * Same sections, with a real "X/Y Online" badge injected onto the Routers
 * item — pass `undefined` (the default, while the count hasn't loaded) to
 * render the plain, badge-less item rather than a placeholder.
 */
export function dashboardSectionsWithRoutersBadge(badge?: ReactNode): SidebarNavSection[] {
  if (!badge) return DASHBOARD_SECTIONS;
  return DASHBOARD_SECTIONS.map((section) => ({
    ...section,
    items: section.items.map((item) => (item.label === "Routers" ? { ...item, badge } : item)),
  }));
}
