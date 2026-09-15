"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface SidebarNavItem {
  label: string;
  href: string;
  icon: ReactNode;
  badge?: ReactNode;
  /** Exact-match the route instead of prefix-match (use for the shell's root/overview link). */
  exact?: boolean;
}

export interface SidebarNavSection {
  title: string;
  items: SidebarNavItem[];
}

export interface SidebarProps {
  brand: ReactNode;
  /** Top-level items rendered above any titled sections (e.g. "Overview"). */
  topItems?: SidebarNavItem[];
  sections: SidebarNavSection[];
  footer?: ReactNode;
  className?: string;
}

function isActive(pathname: string, item: SidebarNavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function NavLink({ item, active }: { item: SidebarNavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-all",
        active
          ? "bg-primary-container text-on-primary-container font-semibold shadow-[0_0_12px_rgba(128,131,255,0.3)]"
          : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
      )}
    >
      <span className="flex items-center gap-3">
        <span className="flex h-5 w-5 items-center justify-center [&>svg]:h-[18px] [&>svg]:w-[18px]">
          {item.icon}
        </span>
        <span>{item.label}</span>
      </span>
      {item.badge ?? (active && <span className="bg-secondary h-1.5 w-1.5 shrink-0 rounded-full" />)}
    </Link>
  );
}

/** Fixed left navigation rail for the tenant dashboard and super-admin shells. */
export function Sidebar({ brand, topItems = [], sections, footer, className }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "bg-surface-container-low fixed left-0 top-0 z-50 flex h-full w-72 flex-col justify-between shadow-[0_1px_8px_rgba(0,0,0,0.2)]",
        className,
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <div className="bg-surface-container-lowest flex h-20 shrink-0 items-center gap-3 px-5">
          {brand}
        </div>

        <nav className="flex flex-col gap-0.5 px-2 py-3">
          {topItems.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(pathname, item)} />
          ))}
        </nav>

        {sections.map((section) => (
          <div key={section.title} className="flex flex-col gap-0.5 px-2 pb-2">
            <div className="px-3 py-2">
              <span className="text-on-surface-variant font-sans text-[0.6875rem] font-bold uppercase tracking-wider">
                {section.title}
              </span>
            </div>
            {section.items.map((item) => (
              <NavLink key={item.href} item={item} active={isActive(pathname, item)} />
            ))}
          </div>
        ))}
      </div>

      {footer && (
        <div className="bg-surface-container-lowest m-2 shrink-0 rounded-xl p-3">{footer}</div>
      )}
    </aside>
  );
}
