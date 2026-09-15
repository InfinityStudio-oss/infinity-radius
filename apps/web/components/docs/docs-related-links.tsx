import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { DOCS_CATEGORIES } from "@/content/docs";

export function DocsRelatedLinks({ slugs }: { slugs: string[] }) {
  const related = slugs
    .map((slug) => DOCS_CATEGORIES.find((category) => category.slug === slug))
    .filter((category): category is NonNullable<typeof category> => Boolean(category));

  if (related.length === 0) return null;

  return (
    <div className="mt-14 border-t border-slate-100 pt-8">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        Related articles
      </p>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {related.map((category) => (
          <Link
            key={category.slug}
            href={`/documentation/${category.slug}`}
            className="group flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition-colors hover:border-blue-200 hover:bg-blue-50"
          >
            {category.navLabel}
            <ArrowRight
              size={15}
              className="text-slate-300 transition-colors group-hover:text-blue-600"
            />
          </Link>
        ))}
      </div>
    </div>
  );
}
