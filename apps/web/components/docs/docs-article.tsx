import type { DocsCategory } from "@/content/docs/types";
import { DocsBlockRenderer } from "./docs-block-renderer";
import { DocsTableOfContents } from "./docs-toc";
import { DocsRelatedLinks } from "./docs-related-links";

export function DocsArticle({ category }: { category: DocsCategory }) {
  const Icon = category.icon;

  return (
    <div className="grid grid-cols-1 gap-10 xl:grid-cols-[1fr_220px]">
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
            <Icon size={18} />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              {category.title}
            </h1>
          </div>
        </div>

        <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-600">
          {category.description}
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
          <span>Updated {category.updated}</span>
          <span aria-hidden="true">&middot;</span>
          <span>For: {category.audience.join(", ")}</span>
        </div>

        <div className="mt-10 space-y-12">
          {category.sections.map((section) => (
            <section key={section.id} id={section.id} className="scroll-mt-24">
              <div className="flex items-center gap-2.5">
                <h2 className="text-lg font-semibold tracking-tight text-slate-900">
                  {section.title}
                </h2>
                {section.status === "coming-soon" && (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                    Coming soon
                  </span>
                )}
              </div>
              <div className="mt-3">
                <DocsBlockRenderer blocks={section.blocks} />
              </div>
            </section>
          ))}
        </div>

        <DocsRelatedLinks slugs={category.related ?? []} />
      </div>

      <DocsTableOfContents sections={category.sections} />
    </div>
  );
}
