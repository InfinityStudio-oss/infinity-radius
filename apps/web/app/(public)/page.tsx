import type { Metadata } from "next";
import Link from "next/link";
import {
  Banknote,
  LineChart,
  Radio,
  Router,
  Ticket,
  Users,
  Wallet,
  Wifi,
} from "lucide-react";
import { HeroProductVisual } from "@/components/public/hero-product-visual";

const TITLE = "Infinity Radius | ISP Billing & WiFi Management Platform";
const DESCRIPTION =
  "Infinity Radius helps ISPs and WiFi operators in Tanzania manage MikroTik networks, RADIUS access, billing, vouchers, collections, payouts and customer operations from one platform.";

export const metadata: Metadata = {
  title: { absolute: TITLE },
  description: DESCRIPTION,
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    type: "website",
  },
};

const PRIMARY_CTA_CLASS =
  "bg-slate-900 text-white inline-flex items-center justify-center rounded-lg px-6 py-3 text-sm font-semibold shadow-sm transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2";
const SECONDARY_CTA_CLASS =
  "border border-slate-300 text-slate-900 hover:bg-slate-50 inline-flex items-center justify-center rounded-lg px-6 py-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2";
const SECONDARY_CTA_DARK_CLASS =
  "border border-white/20 text-white hover:bg-white/10 inline-flex items-center justify-center rounded-lg px-6 py-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900";
const PRIMARY_CTA_ON_DARK_CLASS =
  "bg-white text-slate-900 inline-flex items-center justify-center rounded-lg px-6 py-3 text-sm font-semibold shadow-sm transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900";

const WHY_CARDS = [
  {
    icon: Router,
    title: "Network Operations",
    detail: "Manage hotspot sites, MikroTik routers, RADIUS access and connected sessions.",
  },
  {
    icon: Ticket,
    title: "Billing & Packages",
    detail: "Create flexible internet packages, subscriptions and voucher-based access plans.",
  },
  {
    icon: Banknote,
    title: "Collections & Payouts",
    detail:
      "Accept customer payments, track tenant balances and manage controlled business payouts.",
  },
  {
    icon: Users,
    title: "Customer Management",
    detail: "Manage subscribers, devices, access status, usage and account activity.",
  },
] as const;

const TANZANIA_SUPPORT_ITEMS = [
  "TZS billing",
  "Tanzania phone formats",
  "Local ISP and hotspot operations",
  "Scalable multi-tenant management",
] as const;

const PLATFORM_CAPABILITIES = [
  { icon: Radio, label: "MikroTik & RADIUS" },
  { icon: Wifi, label: "Hotspot Management" },
  { icon: Ticket, label: "Internet Packages" },
  { icon: Ticket, label: "Voucher Management" },
  { icon: Banknote, label: "Customer Billing" },
  { icon: Banknote, label: "Collections" },
  { icon: Wallet, label: "Wallets & Payouts" },
  { icon: LineChart, label: "Reports & Monitoring" },
] as const;

export default function HomePage() {
  return (
    <>
      <section className="bg-white">
        <div className="mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1.15fr_1fr] lg:gap-8 lg:py-24 lg:px-8">
          <div className="flex flex-col">
            <h1 className="text-4xl font-bold leading-[1.1] tracking-tight text-slate-900 sm:text-5xl">
              Manage ISP Billing, WiFi Access &amp; Network Operations Smarter.
            </h1>

            <p className="mt-6 max-w-xl text-base leading-relaxed text-slate-600 sm:text-lg">
              Infinity Radius gives ISPs, WISPs and hotspot operators one platform to manage
              customers, MikroTik networks, internet packages, vouchers, RADIUS access,
              collections and business payouts.
            </p>

            <p className="mt-3 text-sm text-slate-500">
              Built for internet service providers and WiFi operators across Tanzania.
            </p>

            <div className="mt-8 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <Link href="/get-started" className={PRIMARY_CTA_CLASS}>
                Get Started
              </Link>
              <Link href="/features" className={SECONDARY_CTA_CLASS}>
                View Platform Features
              </Link>
            </div>
          </div>

          <HeroProductVisual />
        </div>
      </section>

      <section className="border-t border-slate-100 bg-slate-50">
        <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
          <div className="max-w-2xl">
            <h2 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              Why Infinity Radius?
            </h2>
            <p className="mt-3 text-base leading-relaxed text-slate-600">
              Infinity Radius is built to help internet service providers simplify day-to-day
              network and billing operations from one secure platform.
            </p>
          </div>

          <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {WHY_CARDS.map(({ icon: Icon, title, detail }) => (
              <div key={title} className="rounded-xl border border-slate-200 bg-white p-6">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                  <Icon size={18} />
                </span>
                <p className="mt-4 text-sm font-semibold text-slate-900">{title}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-slate-100 bg-white">
        <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 items-start gap-10 lg:grid-cols-[1fr_1fr] lg:gap-16">
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                Built for ISP &amp; WiFi Operators in Tanzania
              </h2>
              <p className="mt-3 max-w-lg text-base leading-relaxed text-slate-600">
                Infinity Radius is designed for Tanzanian ISPs, WISPs, hotspot operators,
                apartment WiFi providers, hotels, campuses, restaurants and public WiFi networks.
              </p>
            </div>

            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {TANZANIA_SUPPORT_ITEMS.map((item) => (
                <li
                  key={item}
                  className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700"
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-600" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="border-t border-slate-100 bg-slate-50">
        <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
          <h2 className="text-center text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Platform Capabilities
          </h2>

          <div className="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {PLATFORM_CAPABILITIES.map(({ icon: Icon, label }) => (
              <div
                key={label}
                className="flex flex-col items-center gap-2.5 rounded-xl border border-slate-200 bg-white px-4 py-6 text-center"
              >
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                  <Icon size={16} />
                </span>
                <p className="text-xs font-semibold text-slate-800">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-slate-100 bg-slate-900">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center px-4 py-16 text-center sm:px-6 lg:px-8">
          <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Ready to Run Your ISP Smarter?
          </h2>
          <p className="mt-3 max-w-xl text-base leading-relaxed text-slate-300">
            Create your Infinity Radius account and start setting up your network, packages and
            customer access.
          </p>
          <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row">
            <Link href="/get-started" className={PRIMARY_CTA_ON_DARK_CLASS}>
              Get Started
            </Link>
            <Link href="/login" className={SECONDARY_CTA_DARK_CLASS}>
              Sign In
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
