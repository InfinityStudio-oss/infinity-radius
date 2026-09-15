"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PublicLogo } from "@/components/public/public-logo";
import { createClient } from "@/lib/supabase/client";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sessionReady, setSessionReady] = useState<boolean | null>(null);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => setSessionReady(data.session !== null));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    const supabase = createClient();
    const { error: updateError } = await supabase.auth.updateUser({ password });
    setSubmitting(false);

    if (updateError) {
      setError(updateError.message);
      return;
    }

    await supabase.auth.signOut();
    router.push("/login");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-white px-4 py-10 sm:px-6 sm:py-12">
      <div className="w-full max-w-sm sm:max-w-md lg:max-w-lg">
        <Link href="/" className="mb-8 flex items-center justify-center sm:mb-10">
          <PublicLogo variant="full" priority className="h-14 sm:h-16 lg:h-[4.5rem]" />
        </Link>

        <div className="bg-surface border-primary-container/30 rounded-2xl border p-7 shadow-[0_20px_60px_-15px_rgba(13,0,150,0.45)] sm:rounded-[1.75rem] sm:p-9 lg:p-11">
          <h1 className="text-lg font-semibold text-white sm:text-xl lg:text-2xl">
            Set a new password
          </h1>
          <p className="mt-1 text-sm text-white/70 sm:text-base">
            Choose a new password for your Infinity Radius account.
          </p>

          {sessionReady === false ? (
            <p role="alert" className="mt-6 text-sm text-red-300 sm:text-base">
              This reset link is invalid or has expired. Request a new one from the{" "}
              <Link href="/forgot-password" className="underline hover:text-red-200">
                forgot password
              </Link>{" "}
              page.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4 sm:mt-8 sm:gap-5">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="text-xs font-medium text-white/85 sm:text-sm">
                  New password
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="focus:border-primary-container focus:ring-primary/40 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 sm:px-4 sm:py-2.5 sm:text-base"
                  placeholder="••••••••"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="confirmPassword"
                  className="text-xs font-medium text-white/85 sm:text-sm"
                >
                  Confirm new password
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
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
                disabled={submitting || sessionReady !== true}
                className="text-on-primary-container mt-2 inline-flex items-center justify-center rounded-lg bg-white px-4 py-2.5 text-sm font-semibold shadow-[0_0_18px_rgba(128,131,255,0.45)] transition-shadow hover:shadow-[0_0_24px_rgba(128,131,255,0.7)] disabled:cursor-not-allowed disabled:opacity-60 sm:py-3 sm:text-base"
              >
                {submitting ? "Updating…" : "Update password"}
              </button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
