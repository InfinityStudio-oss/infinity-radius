"use client";

import { useState, type ReactNode } from "react";
import { Menu, X } from "lucide-react";
import { DocsSearch } from "./docs-search";
import { DocsSidebarNav } from "./docs-sidebar";

export function DocsLayout({ children }: { children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <a
        href="#docs-content"
        className="sr-only rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60]"
      >
        Skip to content
      </a>

      <div className="flex items-center gap-3 lg:hidden">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          aria-expanded={drawerOpen}
          aria-controls="docs-mobile-nav"
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <Menu size={16} />
          Documentation menu
        </button>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-10 lg:mt-0 lg:grid-cols-[240px_1fr]">
        <aside className="hidden lg:block">
          <div className="border-outline-variant/40 bg-surface sticky top-24 space-y-5 rounded-2xl border p-4">
            <DocsSearch variant="dark" />
            <DocsSidebarNav variant="dark" />
          </div>
        </aside>

        {/* A `div`, not `main` — the (public) route group layout already
            provides the page's single `<main>` landmark; nesting another
            would create two competing landmarks for screen readers. */}
        <div id="docs-content">{children}</div>
      </div>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close documentation menu"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-slate-900/40"
          />
          <div
            id="docs-mobile-nav"
            className="absolute inset-y-0 left-0 w-80 max-w-[85vw] overflow-y-auto bg-white p-5 shadow-xl"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-900">Documentation</p>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close"
                className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>
            <div className="mt-4 space-y-5">
              <DocsSearch />
              <DocsSidebarNav onNavigate={() => setDrawerOpen(false)} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
