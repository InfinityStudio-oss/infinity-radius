import type { ReactNode } from "react";
import Link from "next/link";
import { Logo } from "@infinity-radius/ui";

export function AccountStatusShell({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <Link href="/" className="mb-8 flex items-center justify-center">
          <Logo />
        </Link>

        <div className="border-outline-variant/40 bg-surface-container-low rounded-xl border p-6">
          {children}
        </div>
      </div>
    </main>
  );
}
