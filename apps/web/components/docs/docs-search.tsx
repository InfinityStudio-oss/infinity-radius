"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Search, X } from "lucide-react";
import { cn } from "@infinity-radius/ui";
import { buildDocsSearchIndex } from "@/content/docs";

export interface DocsSearchProps {
  variant?: "light" | "dark";
}

/**
 * Local static search over documentation section titles/snippets only —
 * no external search service, no fabricated results. Matches whatever is
 * actually written in content/docs/*.ts.
 */
export function DocsSearch({ variant = "light" }: DocsSearchProps) {
  const dark = variant === "dark";
  const [query, setQuery] = useState("");
  const index = useMemo(() => buildDocsSearchIndex(), []);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    return index
      .filter(
        (entry) =>
          entry.title.toLowerCase().includes(q) ||
          entry.snippet.toLowerCase().includes(q) ||
          entry.categoryTitle.toLowerCase().includes(q),
      )
      .slice(0, 8);
  }, [query, index]);

  return (
    <div className="relative">
      <div className="relative">
        <Search
          size={15}
          className={cn(
            "pointer-events-none absolute left-3 top-1/2 -translate-y-1/2",
            dark ? "text-on-surface-variant" : "text-slate-400",
          )}
        />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search documentation…"
          aria-label="Search documentation"
          className={cn(
            "w-full rounded-lg border py-2 pl-9 pr-8 text-sm focus-visible:outline-none focus-visible:ring-2",
            dark
              ? "border-outline-variant/60 bg-surface-container-low text-on-surface placeholder:text-on-surface-variant focus-visible:ring-primary"
              : "border-slate-300 bg-white text-slate-900 placeholder:text-slate-400 focus-visible:ring-blue-600",
          )}
        />
        {query && (
          <button
            type="button"
            onClick={() => setQuery("")}
            aria-label="Clear search"
            className={cn(
              "absolute right-2 top-1/2 -translate-y-1/2 rounded p-1",
              dark
                ? "text-on-surface-variant hover:text-on-surface"
                : "text-slate-400 hover:text-slate-600",
            )}
          >
            <X size={14} />
          </button>
        )}
      </div>

      {query.trim().length >= 2 && (
        <div className="absolute left-0 right-0 top-full z-20 mt-2 max-h-80 overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {results.length === 0 ? (
            <p className="px-4 py-3 text-sm text-slate-500">No results for &quot;{query}&quot;.</p>
          ) : (
            <ul>
              {results.map((entry) => (
                <li key={entry.href}>
                  <Link
                    href={entry.href}
                    onClick={() => setQuery("")}
                    className="block px-4 py-2.5 hover:bg-slate-50"
                  >
                    <p className="text-sm font-medium text-slate-900">{entry.title}</p>
                    <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">
                      {entry.categoryTitle} &middot; {entry.snippet}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
