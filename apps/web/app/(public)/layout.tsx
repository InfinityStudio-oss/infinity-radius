import type { ReactNode } from "react";
import { PublicHeader } from "@/components/public/public-header";
import { PublicFooter } from "@/components/public/public-footer";

/**
 * Layout for every public, unauthenticated marketing/informational page
 * (homepage, features, solutions, documentation, status, about, contact,
 * support, terms, privacy, get-started). Deliberately has no auth check —
 * /login, /dashboard, and /super-admin are NOT part of this route group
 * and keep their own existing layouts untouched.
 */
export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-900">
      <PublicHeader />
      <main className="flex-1 pt-16">{children}</main>
      <PublicFooter />
    </div>
  );
}
