import type { ReactNode } from "react";

export interface LegalSection {
  id: string;
  heading: string;
  body: ReactNode;
}

export interface LegalPageProps {
  title: string;
  intro: string;
  effectiveDate: string;
  sections: LegalSection[];
}

/**
 * Shared layout for Privacy Policy / Terms of Service — light theme,
 * centered documentation-width column, auto-generated table of contents
 * from the section list, numbered heading hierarchy.
 */
export function LegalPage({ title, intro, effectiveDate, sections }: LegalPageProps) {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{title}</h1>
      <p className="mt-3 text-sm text-slate-500">Effective date: {effectiveDate}</p>
      <p className="mt-6 text-base leading-relaxed text-slate-600">{intro}</p>

      <nav aria-label="Table of contents" className="mt-10 rounded-xl border border-slate-200 bg-slate-50 p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Table of Contents
        </p>
        <ol className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
          {sections.map((section, index) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                className="text-slate-600 hover:text-blue-600 hover:underline"
              >
                {index + 1}. {section.heading}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <div className="mt-12 space-y-10">
        {sections.map((section, index) => (
          <section key={section.id} id={section.id} className="scroll-mt-24">
            <h2 className="text-xl font-semibold tracking-tight text-slate-900">
              {index + 1}. {section.heading}
            </h2>
            <div className="mt-3 space-y-3 text-sm leading-relaxed text-slate-600">
              {section.body}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
