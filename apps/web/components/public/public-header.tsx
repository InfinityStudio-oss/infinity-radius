"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { cn } from "@infinity-radius/ui";
import { PublicLogo } from "./public-logo";

const NAV_LINKS = [
  { label: "Home", href: "/" },
  { label: "Solutions", href: "/solutions" },
  { label: "Features", href: "/features" },
  { label: "Documentation", href: "/documentation" },
  { label: "Contact", href: "/contact" },
] as const;

const SECONDARY_CTA_CLASS =
  "text-slate-600 hover:text-slate-900 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2";
const PRIMARY_CTA_CLASS =
  "bg-slate-900 text-white inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-semibold shadow-sm transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2";

/**
 * Public marketing site header — light theme, scoped to the (public) route
 * group only. Tenant Dashboard / Super Admin keep their own dark shell
 * (components/shell), untouched by this component.
 */
export function PublicHeader() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  return (
    <header className="fixed left-0 top-0 z-50 w-full border-b border-slate-200 bg-white/95 backdrop-blur-md">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-6 px-4 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="flex items-center rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
          aria-label="Infinity Radius home"
        >
          <PublicLogo priority />
        </Link>

        <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary">
          {NAV_LINKS.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname?.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "relative rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600",
                  active ? "text-slate-900" : "text-slate-600 hover:text-slate-900",
                )}
              >
                {link.label}
                {active && (
                  <span className="absolute inset-x-3 -bottom-[1px] h-0.5 rounded-full bg-blue-600" />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="hidden items-center gap-2 sm:flex">
          <Link href="/login" className={SECONDARY_CTA_CLASS}>
            Sign In
          </Link>
          <Link href="/get-started" className={PRIMARY_CTA_CLASS}>
            Get Started
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setMobileOpen((open) => !open)}
          className="inline-flex items-center justify-center rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 lg:hidden"
          aria-expanded={mobileOpen}
          aria-controls="public-mobile-nav"
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
        >
          {mobileOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      {mobileOpen && (
        <nav
          id="public-mobile-nav"
          aria-label="Mobile"
          className="border-t border-slate-200 bg-white px-4 pb-6 pt-2 lg:hidden"
        >
          <div className="flex flex-col gap-1">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              >
                {link.label}
              </Link>
            ))}
          </div>
          <div className="mt-4 flex flex-col gap-2 border-t border-slate-200 pt-4">
            <Link
              href="/login"
              onClick={() => setMobileOpen(false)}
              className="rounded-lg px-3 py-2.5 text-center text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            >
              Sign In
            </Link>
            <Link
              href="/get-started"
              onClick={() => setMobileOpen(false)}
              className="rounded-lg bg-slate-900 px-3 py-2.5 text-center text-sm font-semibold text-white hover:bg-slate-800"
            >
              Get Started
            </Link>
          </div>
        </nav>
      )}
    </header>
  );
}
