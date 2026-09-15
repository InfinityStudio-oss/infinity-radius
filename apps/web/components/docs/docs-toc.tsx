import type { DocsSection } from "@/content/docs/types";

export function DocsTableOfContents({ sections }: { sections: DocsSection[] }) {
  return (
    <nav aria-label="On this page" className="sticky top-24 hidden xl:block">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">On this page</p>
      <ol className="mt-3 space-y-2 border-l border-slate-200 pl-4 text-sm">
        {sections.map((section) => (
          <li key={section.id}>
            <a href={`#${section.id}`} className="text-slate-500 hover:text-blue-600">
              {section.title}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
