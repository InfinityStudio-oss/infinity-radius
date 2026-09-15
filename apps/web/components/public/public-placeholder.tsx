import type { ReactNode } from "react";

export interface PublicPlaceholderPageProps {
  title: string;
  children: ReactNode;
}

/**
 * Shared shell for every "not built yet" public page (documentation,
 * status, about, contact, support, terms, privacy, ...). Honest and
 * minimal on purpose — never fabricates the content it's standing in for.
 */
export function PublicPlaceholderPage({ title, children }: PublicPlaceholderPageProps) {
  return (
    <div className="mx-auto flex min-h-[60vh] w-full max-w-2xl flex-col justify-center px-4 py-20 sm:px-6 lg:px-8">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{title}</h1>
      <div className="mt-4 space-y-3 text-base leading-relaxed text-slate-600">{children}</div>
    </div>
  );
}
