import type { Metadata } from "next";
import Link from "next/link";
import { Headset, LogIn, Phone } from "lucide-react";
import { PUBLIC_CONTACT } from "@/lib/public-contact";

export const metadata: Metadata = {
  title: "Support",
  description: "Get help from the Infinity Radius support team.",
};

export default function SupportPage() {
  return (
    <div className="mx-auto flex min-h-[60vh] w-full max-w-lg flex-col justify-center px-4 py-20 sm:px-6 lg:px-8">
      <p className="text-xs font-semibold uppercase tracking-widest text-blue-600">Support</p>
      <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
        We&apos;re here to help
      </h1>
      <p className="mt-4 text-base leading-relaxed text-slate-600">
        Reach the Infinity Radius support team directly for help with your ISP or hotspot
        account.
      </p>

      <div className="mt-8 space-y-3">
        <a
          href={`mailto:${PUBLIC_CONTACT.supportEmail}`}
          className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 transition-colors hover:bg-slate-50"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
            <Headset size={16} />
          </span>
          <span className="flex flex-col leading-tight">
            <span className="text-xs font-medium text-slate-400">Support Email</span>
            <span className="text-sm font-semibold text-slate-900">
              {PUBLIC_CONTACT.supportEmail}
            </span>
          </span>
        </a>

        <a
          href={PUBLIC_CONTACT.phoneHref}
          className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 transition-colors hover:bg-slate-50"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
            <Phone size={16} />
          </span>
          <span className="flex flex-col leading-tight">
            <span className="text-xs font-medium text-slate-400">Phone</span>
            <span className="text-sm font-semibold text-slate-900">
              {PUBLIC_CONTACT.phoneDisplay}
            </span>
          </span>
        </a>

        <Link
          href="/login"
          className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 transition-colors hover:bg-slate-50"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
            <LogIn size={16} />
          </span>
          <span className="flex flex-col leading-tight">
            <span className="text-xs font-medium text-slate-400">Existing Clients</span>
            <span className="text-sm font-semibold text-slate-900">Sign In</span>
          </span>
        </Link>
      </div>
    </div>
  );
}
