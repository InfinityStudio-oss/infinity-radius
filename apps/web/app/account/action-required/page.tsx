import { redirect } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { AccountStatusShell } from "@/components/account/account-status-shell";
import { getAccountStatus, requireUser } from "@/lib/auth";

export default async function ActionRequiredPage() {
  await requireUser();
  const status = await getAccountStatus();

  if (status === null) {
    redirect("/login");
  }
  if (status.tenant_status !== "MORE_INFORMATION_REQUIRED") {
    redirect("/account/pending-review");
  }

  const message = status.verification?.more_information_message;

  return (
    <AccountStatusShell>
      <div className="flex flex-col items-center text-center">
        <span className="bg-warning/15 text-warning flex h-12 w-12 items-center justify-center rounded-full">
          <AlertTriangle size={22} />
        </span>
        <h1 className="text-on-surface mt-4 text-lg font-semibold">
          Additional Information Needed
        </h1>
        <p className="text-on-surface-variant mt-2 text-sm leading-relaxed">
          The Infinity Radius team needs a bit more information before your business can be
          approved.
        </p>

        {message && (
          <div className="border-outline-variant/40 bg-surface-container-lowest mt-4 w-full rounded-lg border p-4 text-left">
            <p className="text-on-surface-variant text-xs font-semibold uppercase tracking-wide">
              Message from the Infinity Radius team
            </p>
            <p className="text-on-surface mt-1.5 text-sm">{message}</p>
          </div>
        )}

        <p className="text-on-surface-variant mt-4 text-sm leading-relaxed">
          Self-service editing of your application isn&apos;t available yet — please contact
          support with the requested details and we&apos;ll update your application for you.
        </p>

        <p className="text-on-surface-variant mt-6 text-xs">
          Support: help@infinityradius.com &middot; +255 747 730 270
        </p>
      </div>
    </AccountStatusShell>
  );
}
