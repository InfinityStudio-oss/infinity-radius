import Link from "next/link";
import { Headset, Mail, Phone } from "lucide-react";
import { PublicLogo } from "./public-logo";
import { PUBLIC_CONTACT } from "@/lib/public-contact";

interface FooterColumn {
  title: string;
  links: { label: string; href: string }[];
}

/**
 * Production-safe footer nav — no fabricated stats, claims, physical
 * address, or social links that aren't actually configured anywhere.
 * IMPORTANT: background stays the existing dark surface token
 * (bg-surface-container-lowest) — do not lighten this.
 */
const COMPANY_COLUMN: FooterColumn = {
  title: "Company",
  links: [
    { label: "About Us", href: "/about" },
    { label: "Contact Us", href: "/contact" },
    { label: "Support", href: "/support" },
    { label: "Privacy Policy", href: "/privacy" },
    { label: "Terms of Service", href: "/terms" },
  ],
};

const QUICK_LINKS_COLUMN: FooterColumn = {
  title: "Quick Links",
  links: [
    { label: "Home", href: "/" },
    { label: "Features", href: "/features" },
    { label: "Solutions", href: "/solutions" },
    { label: "Get Started", href: "/get-started" },
    { label: "Sign In", href: "/login" },
    { label: "Documentation", href: "/documentation" },
  ],
};

const PLATFORM_COLUMN: FooterColumn = {
  title: "Platform",
  links: [
    { label: "Network Management", href: "/features#network-management" },
    { label: "Billing & Vouchers", href: "/features#billing-vouchers" },
    { label: "Collections & Payouts", href: "/features#collections-payouts" },
    { label: "MikroTik & RADIUS", href: "/features#mikrotik-radius" },
  ],
};

const FOOTER_COLUMNS: FooterColumn[] = [COMPANY_COLUMN, QUICK_LINKS_COLUMN, PLATFORM_COLUMN];

export function PublicFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-outline-variant/40 bg-surface-container-lowest border-t">
      <div className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-y-10 sm:grid-cols-2 lg:grid-cols-4 lg:gap-x-8">
          <div className="sm:col-span-2 lg:col-span-1">
            <Link href="/" className="inline-flex items-center" aria-label="Infinity Radius home">
              <PublicLogo />
            </Link>
            <p className="text-on-surface-variant mt-4 max-w-xs text-sm leading-relaxed">
              Multi-tenant ISP billing, hotspot and WiFi management platform built for ISPs and
              network operators across Tanzania.
            </p>

            <ul className="mt-5 space-y-2.5">
              <li>
                <a
                  href={`mailto:${PUBLIC_CONTACT.generalEmail}`}
                  className="text-on-surface-variant hover:text-on-surface focus-visible:ring-primary flex items-center gap-2.5 rounded text-sm transition-colors focus-visible:outline-none focus-visible:ring-2"
                >
                  <Mail size={15} className="shrink-0" />
                  <span className="min-w-0 break-all">{PUBLIC_CONTACT.generalEmail}</span>
                </a>
              </li>
              <li>
                <a
                  href={`mailto:${PUBLIC_CONTACT.supportEmail}`}
                  className="text-on-surface-variant hover:text-on-surface focus-visible:ring-primary flex items-center gap-2.5 rounded text-sm transition-colors focus-visible:outline-none focus-visible:ring-2"
                >
                  <Headset size={15} className="shrink-0" />
                  <span className="min-w-0 break-all">{PUBLIC_CONTACT.supportEmail}</span>
                </a>
              </li>
              <li>
                <a
                  href={PUBLIC_CONTACT.phoneHref}
                  className="text-on-surface-variant hover:text-on-surface focus-visible:ring-primary flex items-center gap-2.5 rounded text-sm transition-colors focus-visible:outline-none focus-visible:ring-2"
                >
                  <Phone size={15} className="shrink-0" />
                  <span className="min-w-0">{PUBLIC_CONTACT.phoneDisplay}</span>
                </a>
              </li>
            </ul>
          </div>

          {FOOTER_COLUMNS.map((column) => (
            <div key={column.title}>
              <h3 className="text-on-surface-variant text-xs font-semibold uppercase tracking-wider">
                {column.title}
              </h3>
              <ul className="mt-4 space-y-3">
                {column.links.map((link) => (
                  <li key={`${column.title}-${link.label}`}>
                    <Link
                      href={link.href}
                      className="text-on-surface-variant hover:text-on-surface focus-visible:ring-primary rounded text-sm transition-colors focus-visible:outline-none focus-visible:ring-2"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="border-outline-variant/40 mt-12 flex flex-col gap-3 border-t pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-on-surface-variant text-xs">
            &copy; {year} Infinity Radius. All rights reserved.
          </p>
          <div className="flex items-center gap-4">
            <Link
              href="/privacy"
              className="text-on-surface-variant hover:text-on-surface text-xs transition-colors"
            >
              Privacy Policy
            </Link>
            <Link
              href="/terms"
              className="text-on-surface-variant hover:text-on-surface text-xs transition-colors"
            >
              Terms of Service
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
