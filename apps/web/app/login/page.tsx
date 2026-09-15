"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PublicLogo } from "@/components/public/public-logo";
import { createClient } from "@/lib/supabase/client";
import { apiFetch, ApiClientError } from "@/lib/api-client";
import type { ApiEnvelope, CurrentUserRead } from "@/lib/api-types";

const ACCOUNT_STATUS_REDIRECTS: Record<string, string> = {
  PENDING_VERIFICATION: "/account/pending-review",
  MORE_INFORMATION_REQUIRED: "/account/action-required",
  REJECTED: "/account/rejected",
  SUSPENDED: "/account/suspended",
};

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    const supabase = createClient();
    const { data: signInData, error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (signInError) {
      setSubmitting(false);
      setError(signInError.message);
      return;
    }

    // Route by the database-resolved role/tenant state, never guessed —
    // FastAPI enforces the same restrictions independently either way, so
    // a wrong guess here would just be redirected again, not a security gap.
    const accessToken = signInData.session?.access_token ?? null;
    try {
      const envelope = await apiFetch<ApiEnvelope<CurrentUserRead>>("/api/v1/auth/me", {
        accessToken,
      });
      const view = envelope.data;

      const accountRedirect = view.tenant_status
        ? ACCOUNT_STATUS_REDIRECTS[view.tenant_status]
        : undefined;

      if (view.roles.includes("SUPER_ADMIN")) {
        router.push("/super-admin");
      } else if (view.tenant_status === "ACTIVE") {
        router.push("/dashboard");
      } else if (accountRedirect) {
        router.push(accountRedirect);
      } else {
        router.push("/dashboard");
      }
    } catch (viewError) {
      setSubmitting(false);
      setError(
        viewError instanceof ApiClientError
          ? viewError.message
          : "Signed in, but couldn't load your account. Please try again.",
      );
      return;
    }

    router.refresh();
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-white px-4 py-10 sm:px-6 sm:py-12">
      <div className="w-full max-w-sm sm:max-w-md lg:max-w-lg">
        <Link href="/" className="mb-8 flex items-center justify-center sm:mb-10">
          <PublicLogo variant="full" priority className="h-14 sm:h-16 lg:h-[4.5rem]" />
        </Link>

        <div className="bg-surface border-primary-container/30 rounded-2xl border p-7 shadow-[0_20px_60px_-15px_rgba(13,0,150,0.45)] sm:rounded-[1.75rem] sm:p-9 lg:p-11">
          <h1 className="text-lg font-semibold text-white sm:text-xl lg:text-2xl">Sign in</h1>
          <p className="mt-1 text-sm text-white/70 sm:text-base">
            Access your Infinity Radius workspace.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4 sm:mt-8 sm:gap-5">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="text-xs font-medium text-white/85 sm:text-sm">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="focus:border-primary-container focus:ring-primary/40 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 sm:px-4 sm:py-2.5 sm:text-base"
                placeholder="you@company.co.tz"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <label htmlFor="password" className="text-xs font-medium text-white/85 sm:text-sm">
                  Password
                </label>
                <Link
                  href="/forgot-password"
                  className="text-xs font-medium text-white hover:underline sm:text-sm"
                >
                  Forgot password?
                </Link>
              </div>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="focus:border-primary-container focus:ring-primary/40 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 sm:px-4 sm:py-2.5 sm:text-base"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="text-on-primary-container mt-2 inline-flex items-center justify-center rounded-lg bg-white px-4 py-2.5 text-sm font-semibold shadow-[0_0_18px_rgba(128,131,255,0.45)] transition-shadow hover:shadow-[0_0_24px_rgba(128,131,255,0.7)] disabled:cursor-not-allowed disabled:opacity-60 sm:py-3 sm:text-base"
            >
              {submitting ? "Signing in…" : "Sign In"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
