import {
  LayoutDashboard,
  Building2,
  Layers,
  Radio,
  Router,
  RadioTower,
  ServerCog,
  ScrollText,
  HandCoins,
  Wallet,
  Send,
  Scale,
  LifeBuoy,
  History,
  HeartPulse,
  Settings,
} from "lucide-react";
import type { SidebarNavSection } from "@infinity-radius/ui";

export const SUPER_ADMIN_SECTIONS: SidebarNavSection[] = [
  {
    title: "Platform Overview",
    items: [
      { label: "Dashboard", href: "/super-admin", icon: <LayoutDashboard />, exact: true },
      { label: "Tenants", href: "/super-admin/tenants", icon: <Building2 /> },
      { label: "Tenant Plans", href: "/super-admin/tenant-plans", icon: <Layers /> },
    ],
  },
  {
    title: "Network & Infrastructure",
    items: [
      { label: "Hotspot Sites", href: "/super-admin/network/hotspot-sites", icon: <Radio /> },
      { label: "Routers", href: "/super-admin/network/routers", icon: <Router /> },
      { label: "RADIUS", href: "/super-admin/network/radius", icon: <RadioTower /> },
      { label: "Network Agents", href: "/super-admin/network/agents", icon: <ServerCog /> },
      { label: "System Logs", href: "/super-admin/network/system-logs", icon: <ScrollText /> },
    ],
  },
  {
    title: "Financial & Billing",
    items: [
      { label: "Collections", href: "/super-admin/financial/collections", icon: <HandCoins /> },
      { label: "Wallets", href: "/super-admin/financial/wallets", icon: <Wallet /> },
      { label: "Disbursements", href: "/super-admin/financial/disbursements", icon: <Send /> },
      { label: "Reconciliation", href: "/super-admin/financial/reconciliation", icon: <Scale /> },
    ],
  },
  {
    title: "Operations",
    items: [
      { label: "Support", href: "/super-admin/operations/support", icon: <LifeBuoy /> },
      { label: "Audit Logs", href: "/super-admin/operations/audit-logs", icon: <History /> },
      {
        label: "System Health",
        href: "/super-admin/operations/system-health",
        icon: <HeartPulse />,
      },
      { label: "Settings", href: "/super-admin/operations/settings", icon: <Settings /> },
    ],
  },
];
