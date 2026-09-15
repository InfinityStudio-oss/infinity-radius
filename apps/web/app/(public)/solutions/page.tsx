import type { Metadata } from "next";
import {
  Building,
  Building2,
  Coffee,
  Hotel,
  Landmark,
  School,
  Users,
  Wifi,
  Wrench,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Solutions",
  description:
    "Infinity Radius solutions for ISPs, WISPs, hotspot operators, apartment and hotel WiFi, campuses, restaurants and cafes, property managers, and public WiFi operators.",
};

const AUDIENCES = [
  {
    icon: Wifi,
    title: "ISPs",
    detail: "Run billing, packages, and network operations for a wired or fixed-wireless ISP.",
  },
  {
    icon: Wrench,
    title: "WISPs",
    detail: "Manage fixed-wireless customer bases with MikroTik-based network integration.",
  },
  {
    icon: Landmark,
    title: "Hotspot Operators",
    detail: "Sell vouchers and manage prepaid hotspot access across one or many sites.",
  },
  {
    icon: Building,
    title: "Apartment WiFi",
    detail: "Offer managed WiFi access to residents with per-unit billing and packages.",
  },
  {
    icon: Hotel,
    title: "Hotels",
    detail: "Provide guest WiFi access alongside vouchers and package-based tiers.",
  },
  {
    icon: School,
    title: "Campuses",
    detail: "Manage network access and billing across large, multi-building sites.",
  },
  {
    icon: Coffee,
    title: "Restaurants & Cafes",
    detail: "Offer simple voucher-based WiFi access for customers on site.",
  },
  {
    icon: Building2,
    title: "Property Managers",
    detail: "Centrally manage WiFi and billing across multiple managed properties.",
  },
  {
    icon: Users,
    title: "Public WiFi Operators",
    detail: "Run public-access hotspot networks with voucher and package controls.",
  },
] as const;

export default function SolutionsPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
      <div className="max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-widest text-blue-600">Solutions</p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Built for how you operate your network.
        </h1>
        <p className="mt-4 text-base leading-relaxed text-slate-600">
          Infinity Radius adapts to a range of ISP and WiFi operator business models, from
          large-scale network operators to single-site hotspot businesses.
        </p>
      </div>

      <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {AUDIENCES.map(({ icon: Icon, title, detail }) => (
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
  );
}
