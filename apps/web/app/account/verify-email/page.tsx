"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { MailCheck } from "lucide-react";
import { AccountStatusShell } from "@/components/account/account-status-shell";
import { apiMutate, ApiClientError } from "@/lib/api-client";

const RESEND_COOLDOWN_SECONDS = 60;

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const email = searchParams.get("email") ?? "";
  const [cooldown, setCooldown] = useState(0);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleResend() {
    if (!email || cooldown > 0 || sending) return;
    setSending(true);
    setMessage(null);
    try {
      await apiMutate("/api/v1/onboarding/resend-verification-email", { body: { email } });
      setMessage("Verification email sent — please check your inbox.");
      setCooldown(RESEND_COOLDOWN_SECONDS);
      const interval = setInterval(() => {
        setCooldown((current) => {
          if (current <= 1) {
            clearInterval(interval);
            return 0;
          }
          return current - 1;
        });
      }, 1000);
    } catch (error) {
      setMessage(
        error instanceof ApiClientError
          ? error.message
          : "Couldn't send the email right now — please try again shortly.",
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <AccountStatusShell>
      <div className="flex flex-col items-center text-center">
        <span className="bg-primary-container/15 text-primary flex h-12 w-12 items-center justify-center rounded-full">
          <MailCheck size={22} />
        </span>
        <h1 className="text-on-surface mt-4 text-lg font-semibold">Account Created</h1>
        <p className="text-on-surface-variant mt-2 text-sm leading-relaxed">
          Please check your email to verify your Infinity Radius account.
        </p>
        <p className="text-on-surface-variant mt-3 text-sm leading-relaxed">
          Your business details have also been submitted for platform review. You will be able
          to access the tenant dashboard once your email is verified and the Infinity Radius
          team approves your business.
        </p>

        {email && (
          <button
            type="button"
            onClick={handleResend}
            disabled={sending || cooldown > 0}
            className="border-outline-variant text-on-surface hover:bg-surface-container mt-6 inline-flex items-center justify-center rounded-lg border px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
          >
            {cooldown > 0
              ? `Resend verification email (${cooldown}s)`
              : sending
                ? "Sending…"
                : "Resend verification email"}
          </button>
        )}
        {message && <p className="text-on-surface-variant mt-3 text-xs">{message}</p>}

        <p className="text-on-surface-variant mt-6 text-xs">
          Support: help@infinityradius.com &middot; +255 747 730 270
        </p>
      </div>
    </AccountStatusShell>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
