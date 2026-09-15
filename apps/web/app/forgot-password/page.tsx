"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { PublicLogo } from "@/components/public/public-logo";
import { createClient } from "@/lib/supabase/client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    const supabase = createClient();
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });

    setSubmitting(false);

    if (resetError) {
      setError(resetError.message);
      return;
    }

    setSent(true);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-white px-4 py-10 sm:px-6 sm:py-12">
      <div className="w-full max-w-sm sm:max-w-md lg:max-w-lg">
        <Link href="/" className="mb-8 flex items-center justify-center sm:mb-10">
          <PublicLogo variant="full" priority className="h-14 sm:h-16 lg:h-[4.5rem]" />
        </Link>

        <div className="bg-surface border-primary-container/30 rounded-2xl border p-7 shadow-[0_20px_60px_-15px_rgba(13,0,150,0.45)] sm:rounded-[1.75rem] sm:p-9 lg:p-11">
          <h1 className="text-lg font-semibold text-white sm:text-xl lg:text-2xl">
            Reset your password
          </h1>
          <p className="mt-1 text-sm text-white/70 sm:text-base">
            Enter your email and we&apos;ll send you a link to reset your password.
          </p>

          {sent ? (
            <p className="mt-6 text-sm text-white/90 sm:text-base" role="status">
              If an account exists for {email}, a reset link is on its way.
            </p>
          ) : (
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
                {submitting ? "Sending…" : "Send reset link"}
              </button>
            </form>
          )}

          <Link
            href="/login"
            className="mt-6 block text-center text-sm text-white/70 hover:text-white sm:text-base"
          >
            Back to sign in
          </Link>
        </div>
      </div>
    </main>
  );
}
