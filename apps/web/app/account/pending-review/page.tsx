import { redirect } from "next/navigation";
import { CheckCircle2, Circle } from "lucide-react";
import { AccountStatusShell } from "@/components/account/account-status-shell";
import { getAccountStatus, requireUser } from "@/lib/auth";

const OTHER_STATUS_REDIRECTS: Record<string, string> = {
  MORE_INFORMATION_REQUIRED: "/account/action-required",
  REJECTED: "/account/rejected",
  SUSPENDED: "/account/suspended",
};

function ChecklistRow({ label, complete }: { label: string; complete: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      {complete ? (
        <CheckCircle2 size={16} className="text-success shrink-0" />
      ) : (
        <Circle size={16} className="text-outline shrink-0" />
      )}
      <span className={complete ? "text-on-surface text-sm" : "text-on-surface-variant text-sm"}>
        {label}
      </span>
      <span className="text-on-surface-variant ml-auto text-xs">
        {complete ? "complete" : "pending"}
      </span>
    </div>
  );
}

export default async function PendingReviewPage() {
  await requireUser();
  const status = await getAccountStatus();

  if (status === null) {
    redirect("/login");
  }
  if (status.tenant_status === "ACTIVE") {
    redirect("/dashboard");
  }
  const otherRedirect = OTHER_STATUS_REDIRECTS[status.tenant_status];
  if (otherRedirect) {
    redirect(otherRedirect);
  }

  return (
    <AccountStatusShell>
      <h1 className="text-on-surface text-lg font-semibold">Application Under Review</h1>
      <p className="text-on-surface-variant mt-1 text-sm">
        Here&apos;s where your Infinity Radius account stands.
      </p>

      <div className="mt-6 space-y-3">
        <ChecklistRow label="Account Created" complete />
        <ChecklistRow label="Email Verified" complete={status.email_verified} />
        <ChecklistRow label="Business Review" complete={false} />
        <ChecklistRow label="Platform Access" complete={false} />
      </div>

      <p className="text-on-surface-variant mt-6 text-xs">
        Support: help@infinityradius.com &middot; +255 747 730 270
      </p>
    </AccountStatusShell>
  );
}
