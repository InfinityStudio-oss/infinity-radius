import { redirect } from "next/navigation";
import { ShieldOff } from "lucide-react";
import { AccountStatusShell } from "@/components/account/account-status-shell";
import { getAccountStatus, requireUser } from "@/lib/auth";

export default async function SuspendedPage() {
  await requireUser();
  const status = await getAccountStatus();

  if (status === null) {
    redirect("/login");
  }
  if (status.tenant_status !== "SUSPENDED") {
    redirect("/account/pending-review");
  }

  return (
    <AccountStatusShell>
      <div className="flex flex-col items-center text-center">
        <span className="bg-error/15 text-error flex h-12 w-12 items-center justify-center rounded-full">
          <ShieldOff size={22} />
        </span>
        <h1 className="text-on-surface mt-4 text-lg font-semibold">Account Suspended</h1>
        <p className="text-on-surface-variant mt-2 text-sm leading-relaxed">
          Your Infinity Radius account has been suspended and dashboard access is currently
          restricted. Please contact support if you have questions about this.
        </p>
        <p className="text-on-surface-variant mt-6 text-xs">
          Support: help@infinityradius.com &middot; +255 747 730 270
        </p>
      </div>
    </AccountStatusShell>
  );
}
