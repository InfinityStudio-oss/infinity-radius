import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { DocsLayout } from "@/components/docs/docs-layout";
import { DOCS_CATEGORIES } from "@/content/docs";
import { PUBLIC_CONTACT } from "@/lib/public-contact";

const TITLE = "Infinity Radius Documentation";

export const metadata: Metadata = {
  title: "Documentation",
  description:
    "Documentation for Infinity Radius: setting up routers, packages and vouchers, the captive portal, collections, wallets, and payouts.",
  openGraph: { title: TITLE },
};

export default function DocumentationHubPage() {
  return (
    <DocsLayout>
      <p className="text-xs font-semibold uppercase tracking-widest text-blue-600">
        Documentation
      </p>
      <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
        Set up and operate Infinity Radius
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-600">
        Practical guides for ISP owners, WISP owners, hotspot operators, tenant admins, network
        technicians, accountants, and customer care staff — from your first login to running
        collections and payouts day to day.
      </p>

      <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {DOCS_CATEGORIES.map((category) => {
          const Icon = category.icon;
          return (
            <Link
              key={category.slug}
              href={`/documentation/${category.slug}`}
              className="group flex flex-col rounded-xl border border-slate-200 bg-white p-5 transition-colors hover:border-blue-200 hover:bg-blue-50/40"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                <Icon size={17} />
              </span>
              <p className="mt-3 flex items-center gap-1.5 text-sm font-semibold text-slate-900">
                {category.navLabel}
                <ArrowRight
                  size={14}
                  className="text-slate-300 transition-colors group-hover:text-blue-600"
                />
              </p>
              <p className="mt-1 text-sm leading-relaxed text-slate-600">{category.description}</p>
            </Link>
          );
        })}
      </div>

      <div className="mt-14 rounded-xl border border-slate-200 bg-slate-50 p-6">
        <p className="text-sm font-semibold text-slate-900">Can&apos;t find what you need?</p>
        <p className="mt-1.5 text-sm text-slate-600">
          Reach Infinity Radius support at{" "}
          <a
            href={`mailto:${PUBLIC_CONTACT.supportEmail}`}
            className="text-blue-600 hover:underline"
          >
            {PUBLIC_CONTACT.supportEmail}
          </a>{" "}
          or{" "}
          <a href={PUBLIC_CONTACT.phoneHref} className="text-blue-600 hover:underline">
            {PUBLIC_CONTACT.phoneDisplay}
          </a>
          .
        </p>
      </div>
    </DocsLayout>
  );
}
