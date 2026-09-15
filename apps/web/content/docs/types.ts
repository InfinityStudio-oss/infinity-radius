import type { LucideIcon } from "lucide-react";

/**
 * Typed documentation content model (plain TS, not MDX — the project has
 * no MDX/markdown compiler installed, so this avoids adding new build
 * tooling for a first pass). Content lives under content/docs/*.ts, one
 * file per category, aggregated by content/docs/index.ts.
 */
export type DocsBlock =
  | { type: "p"; text: string }
  | { type: "list"; items: string[] }
  | { type: "steps"; items: string[] }
  | { type: "callout"; tone: "info" | "warning" | "note"; text: string }
  | { type: "code"; label?: string; code: string };

export interface DocsSection {
  id: string;
  title: string;
  status?: "available" | "coming-soon";
  blocks: DocsBlock[];
}

export interface DocsCategory {
  slug: string;
  title: string;
  navLabel: string;
  description: string;
  icon: LucideIcon;
  audience: string[];
  updated: string;
  sections: DocsSection[];
  related?: string[];
}
