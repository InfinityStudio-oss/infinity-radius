import { redirect } from "next/navigation";
import { XCircle } from "lucide-react";
import { AccountStatusShell } from "@/components/account/account-status-shell";
import { getAccountStatus, requireUser } from "@/lib/auth";

export default async function RejectedPage() {
  await requireUser();
  const status = await getAccountStatus();

  if (status === null) {
    redirect("/login");
  }
  if (status.tenant_status !== "REJECTED") {
    redirect("/account/pending-review");
  }

  const reason = status.verification?.rejection_reason;

  return (
    <AccountStatusShell>
      <div className="flex flex-col items-center text-center">
        <span className="bg-error/15 text-error flex h-12 w-12 items-center justify-center rounded-full">
          <XCircle size={22} />
        </span>
        <h1 className="text-on-surface mt-4 text-lg font-semibold">Application Not Approved</h1>
        <p className="text-on-surface-variant mt-2 text-sm leading-relaxed">
          After review, we&apos;re unable to approve your Infinity Radius business application at
          this time.
        </p>

        {reason && (
          <div className="border-outline-variant/40 bg-surface-container-lowest mt-4 w-full rounded-lg border p-4 text-left">
            <p className="text-on-surface-variant text-xs font-semibold uppercase tracking-wide">
              Reason
            </p>
            <p className="text-on-surface mt-1.5 text-sm">{reason}</p>
          </div>
        )}

        <p className="text-on-surface-variant mt-4 text-sm leading-relaxed">
          If you believe this is a mistake or would like to discuss it, please contact support.
        </p>
        <p className="text-on-surface-variant mt-6 text-xs">
          Support: help@infinityradius.com &middot; +255 747 730 270
        </p>
      </div>
    </AccountStatusShell>
  );
}
