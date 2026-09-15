import { account } from "./account";
import { captivePortal } from "./captive-portal";
import { collections } from "./collections";
import { customers } from "./customers";
import { gettingStarted } from "./getting-started";
import { mikrotik } from "./mikrotik";
import { packages } from "./packages";
import { payouts } from "./payouts";
import { radius } from "./radius";
import { reports } from "./reports";
import { troubleshooting } from "./troubleshooting";
import { vouchers } from "./vouchers";
import { wallet } from "./wallet";
import { wireguard } from "./wireguard";
import type { DocsCategory } from "./types";

export type { DocsBlock, DocsCategory, DocsSection } from "./types";

/** Sidebar / hub order — intentionally not alphabetical, follows the
 * tenant's real operational journey from signup through to support. */
export const DOCS_CATEGORIES: DocsCategory[] = [
  gettingStarted,
  account,
  mikrotik,
  wireguard,
  radius,
  customers,
  packages,
  vouchers,
  captivePortal,
  collections,
  wallet,
  payouts,
  reports,
  troubleshooting,
];

export function getDocsCategory(slug: string): DocsCategory | undefined {
  return DOCS_CATEGORIES.find((category) => category.slug === slug);
}

export interface DocsSearchEntry {
  categorySlug: string;
  categoryTitle: string;
  sectionId: string;
  title: string;
  snippet: string;
  href: string;
}

/** Local static search index over category/section titles and their first
 * paragraph/list text — no fabricated results, just what's actually
 * written on the page. */
export function buildDocsSearchIndex(): DocsSearchEntry[] {
  const entries: DocsSearchEntry[] = [];

  for (const category of DOCS_CATEGORIES) {
    for (const section of category.sections) {
      const firstTextBlock = section.blocks.find(
        (block) => block.type === "p" || block.type === "callout",
      );
      const snippet =
        firstTextBlock && "text" in firstTextBlock
          ? firstTextBlock.text
          : category.description;

      entries.push({
        categorySlug: category.slug,
        categoryTitle: category.title,
        sectionId: section.id,
        title: section.title,
        snippet,
        href: `/documentation/${category.slug}#${section.id}`,
      });
    }
  }

  return entries;
}
