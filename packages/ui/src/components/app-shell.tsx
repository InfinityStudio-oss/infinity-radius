"use client";

import { cloneElement, useState, type ReactElement, type ReactNode } from "react";
import { cn } from "../lib/cn";

export interface AppShellProps {
  sidebar: ReactElement<{ className?: string }>;
  /** Render prop so TopBar can receive the mobile menu toggle button. */
  topBar: (mobileMenuButton: ReactNode) => ReactNode;
  children: ReactNode;
  /** Extra class(es) on the wrapper around topBar + main (never the
   * sidebar) — e.g. a shell-specific theme scope class. Defaults to
   * nothing, so existing consumers are unaffected. */
  contentClassName?: string;
}

/**
 * Combines Sidebar + TopBar with the standard 288px (w-72) content offset,
 * and owns the mobile drawer open/close state — collapsed off-canvas by
 * default below the lg breakpoint, permanently visible above it.
 */
export function AppShell({ sidebar, topBar, children, contentClassName }: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="bg-background min-h-screen">
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {cloneElement(sidebar, {
        className: cn(
          "transition-transform duration-200 lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          sidebar.props.className,
        ),
      })}

      <div className={cn("lg:pl-72", contentClassName)}>
        {topBar(
          <button
            type="button"
            onClick={() => setMobileOpen((open) => !open)}
            className="text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface flex h-9 w-9 items-center justify-center rounded-lg lg:hidden"
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="h-5 w-5"
            >
              {mobileOpen ? (
                <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" />
              ) : (
                <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
              )}
            </svg>
          </button>,
        )}

        {/* Explicit bg-surface (not just relying on the transparent
            default showing through to the outer shell div) — that outer
            div sits OUTSIDE contentClassName's scope, so a theme scope
            like .super-admin-light applied via contentClassName would
            otherwise never actually paint this element; individual cards/
            panels with their own explicit background already picked up
            the scope correctly, which is what made this gap so easy to
            miss — the canvas behind them didn't. Uses bg-surface (not
            bg-background) because bg-background was never referenced by
            any class in this codebase and Tailwind's content scanner
            never emitted the utility for it as a result — bg-surface has
            the identical root value and is already a proven-generated
            utility elsewhere. */}
        <main className="bg-surface min-h-screen w-full px-4 pb-16 pt-24 sm:px-6">
          {children}
        </main>
      </div>
    </div>
  );
}
