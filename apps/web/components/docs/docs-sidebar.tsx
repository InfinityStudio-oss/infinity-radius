"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@infinity-radius/ui";
import { DOCS_CATEGORIES } from "@/content/docs";

export interface DocsSidebarNavProps {
  onNavigate?: () => void;
  variant?: "light" | "dark";
}

export function DocsSidebarNav({ onNavigate, variant = "light" }: DocsSidebarNavProps) {
  const pathname = usePathname();
  const dark = variant === "dark";

  return (
    <nav aria-label="Documentation" className="space-y-0.5">
      <Link
        href="/documentation"
        onClick={onNavigate}
        className={cn(
          "block rounded-lg px-3 py-2 text-sm font-semibold transition-colors",
          pathname === "/documentation"
            ? dark
              ? "bg-primary-container/15 text-primary"
              : "bg-blue-50 text-blue-700"
            : dark
              ? "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
              : "text-slate-700 hover:bg-slate-100",
        )}
      >
        Overview
      </Link>

      {DOCS_CATEGORIES.map((category) => {
        const href = `/documentation/${category.slug}`;
        const active = pathname === href;
        return (
          <Link
            key={category.slug}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "block rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              active
                ? dark
                  ? "bg-primary-container/15 text-primary"
                  : "bg-blue-50 text-blue-700"
                : dark
                  ? "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                  : "text-slate-600 hover:bg-slate-100",
            )}
          >
            {category.navLabel}
          </Link>
        );
      })}
    </nav>
  );
}
