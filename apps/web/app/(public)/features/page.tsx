import type { Metadata } from "next";
import {
  Banknote,
  Building2,
  LineChart,
  Radio,
  Router,
  Ticket,
  Users,
  Wallet,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Features",
  description:
    "An overview of the Infinity Radius platform: ISP management, network operations, MikroTik and RADIUS integration, packages and vouchers, collections, wallets and payouts, reporting, and multi-tenant administration.",
};

const CATEGORIES = [
  {
    id: undefined as string | undefined,
    icon: Building2,
    title: "ISP Management",
    detail:
      "Manage your ISP or hotspot business from a single workspace — customers, staff accounts, packages, and day-to-day operations in one place.",
  },
  {
    id: "network-management",
    icon: Router,
    title: "Network Operations",
    detail:
      "Monitor connected routers and hotspot sites, track network health, and keep visibility over your infrastructure as it grows.",
  },
  {
    id: "mikrotik-radius",
    icon: Radio,
    title: "MikroTik & RADIUS",
    detail:
      "Connect MikroTik routers and authenticate customer sessions through built-in RADIUS access control, without standing up separate infrastructure.",
  },
  {
    id: "billing-vouchers",
    icon: Ticket,
    title: "Packages & Vouchers",
    detail:
      "Configure internet packages and generate vouchers for prepaid or offline sales, tailored to how your business sells access.",
  },
  {
    id: "collections-payouts",
    icon: Banknote,
    title: "Collections",
    detail:
      "Collect customer payments through integrated collection channels, with every transaction recorded against the right customer and package.",
  },
  {
    id: undefined as string | undefined,
    icon: Wallet,
    title: "Wallets & Payouts",
    detail:
      "Track your available balance in a tenant wallet and request payouts, with controlled approval steps for outgoing disbursements.",
  },
  {
    id: undefined as string | undefined,
    icon: LineChart,
    title: "Reporting",
    detail:
      "Review collections, session, and network trends over time to understand how your business and network are performing.",
  },
  {
    id: undefined as string | undefined,
    icon: Users,
    title: "Multi-Tenant Administration",
    detail:
      "Each ISP or operator runs in its own isolated tenant workspace, with role-based staff access and data kept separate from every other tenant.",
  },
] as const;

export default function FeaturesPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
      <div className="max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-widest text-blue-600">Platform</p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Everything an ISP or hotspot operator needs, in one platform.
        </h1>
        <p className="mt-4 text-base leading-relaxed text-slate-600">
          Infinity Radius brings together the tools ISPs, WISPs, and hotspot operators use to run
          their business — from network operations to billing to business payouts.
        </p>
      </div>

      <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {CATEGORIES.map(({ id, icon: Icon, title, detail }) => (
          <div
            key={title}
            id={id}
            className="scroll-mt-24 rounded-xl border border-slate-200 bg-white p-6"
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
              <Icon size={18} />
            </span>
            <p className="mt-4 text-sm font-semibold text-slate-900">{title}</p>
            <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{detail}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
