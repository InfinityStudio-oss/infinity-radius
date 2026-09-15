"use client";

import { useState } from "react";
import { use as usePromise } from "react";
import { ErrorState, PageHeader } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";
import { useAccessToken } from "@/lib/hooks/use-access-token";
import { apiMutate, ApiClientError } from "@/lib/api-client";

interface TenantDetail {
  tenant: {
    id: string;
    name: string;
    legal_name: string | null;
    business_type: string | null;
    business_email: string | null;
    business_phone: string | null;
    tin: string | null;
    business_license_number: string | null;
    region: string | null;
    district: string | null;
    ward: string | null;
    street_area: string | null;
    address: string | null;
    status: string;
    created_at: string;
  };
  owner_name: string | null;
  owner_email: string | null;
  owner_phone: string | null;
  owner_missing: boolean;
  authorized_contact_name: string | null;
  email_verified: boolean;
  collection_enabled: boolean;
  payout_enabled: boolean;
  verification: {
    status: string;
    submitted_at: string | null;
    reviewed_at: string | null;
    approved_at: string | null;
    rejected_at: string | null;
    rejection_reason: string | null;
    more_information_message: string | null;
  } | null;
  recent_audit_logs: { action: string; created_at: string; actor_id: string | null }[];
}

interface DetailEnvelope {
  success: boolean;
  data: TenantDetail;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-outline-variant/40 bg-surface-container-low rounded-lg border p-4">
      <h2 className="text-on-surface-variant text-xs font-semibold uppercase tracking-wider">
        {title}
      </h2>
      <div className="mt-3 space-y-1.5 text-sm">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-on-surface-variant">{label}</span>
      <span className="text-on-surface font-medium">{value || "—"}</span>
    </div>
  );
}

function FlagToggle({
  label,
  description,
  enabled,
  disabled,
  onToggle,
}: {
  label: string;
  description: string;
  enabled: boolean;
  disabled: boolean;
  onToggle: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <p className="text-on-surface text-sm font-medium">{label}</p>
        <p className="text-on-surface-variant text-xs">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        onClick={() => onToggle(!enabled)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-60 ${
          enabled ? "bg-success" : "bg-surface-container-high"
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
            enabled ? "translate-x-[22px]" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  );
}

export default function TenantReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = usePromise(params);
  const { token } = useAccessToken();
  const { state, data, error, refetch } = useApiQuery<DetailEnvelope>(
    `/api/v1/admin/tenants/${id}`,
  );

  const [pendingAction, setPendingAction] = useState<"reject" | "more-info" | null>(null);
  const [reasonText, setReasonText] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function runAction(path: string, body?: object) {
    setSubmitting(true);
    setActionError(null);
    try {
      await apiMutate(`/api/v1/admin/tenants/${id}${path}`, {
        accessToken: token,
        body: body ?? {},
      });
      setPendingAction(null);
      setReasonText("");
      refetch();
    } catch (err) {
      setActionError(err instanceof ApiClientError ? err.message : "Action failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (state === "error") {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Tenant Review" />
        <ErrorState title="Unable to load tenant" description={error?.message} onRetry={refetch} />
      </div>
    );
  }

  if (state === "loading" || !data) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Tenant Review" />
        <p className="text-on-surface-variant text-sm">Loading…</p>
      </div>
    );
  }

  const { tenant, verification } = data.data;
  const canReview = tenant.status === "PENDING_VERIFICATION" || tenant.status === "MORE_INFORMATION_REQUIRED";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={tenant.name}
        description={`Status: ${tenant.status.replaceAll("_", " ")}`}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Section title="Business Information">
          <Row label="Trading Name" value={tenant.name} />
          <Row label="Legal Name" value={tenant.legal_name} />
          <Row label="Business Type" value={tenant.business_type} />
          <Row label="Business Email" value={tenant.business_email} />
          <Row label="Business Phone" value={tenant.business_phone} />
        </Section>

        <Section title="Owner Information">
          {data.data.owner_missing ? (
            <p className="text-warning text-sm font-medium">Owner record missing</p>
          ) : (
            <>
              <Row label="Name" value={data.data.owner_name} />
              <Row label="Email" value={data.data.owner_email} />
              <Row label="Phone" value={data.data.owner_phone} />
            </>
          )}
        </Section>

        <Section title="Authorized Contact">
          {data.data.owner_missing && !data.data.authorized_contact_name ? (
            <p className="text-warning text-sm font-medium">No tenant owner linked</p>
          ) : (
            <Row label="Name" value={data.data.authorized_contact_name} />
          )}
        </Section>

        <Section title="Location">
          <Row label="Region" value={tenant.region} />
          <Row label="District" value={tenant.district} />
          <Row label="Ward" value={tenant.ward} />
          <Row label="Street / Area" value={tenant.street_area} />
          <Row label="Address" value={tenant.address} />
        </Section>

        <Section title="TIN & Business Licence">
          <Row label="TIN" value={tenant.tin} />
          <Row label="Business Licence Number" value={tenant.business_license_number} />
        </Section>

        <Section title="Email Verification Status">
          <Row label="Email Verified" value={data.data.email_verified ? "Yes" : "No"} />
          <Row label="Signup Date" value={new Date(tenant.created_at).toLocaleString()} />
        </Section>

        <Section title="Verification Timeline">
          <Row label="Submitted" value={verification?.submitted_at ? new Date(verification.submitted_at).toLocaleString() : null} />
          <Row label="Reviewed" value={verification?.reviewed_at ? new Date(verification.reviewed_at).toLocaleString() : null} />
          <Row label="Approved" value={verification?.approved_at ? new Date(verification.approved_at).toLocaleString() : null} />
          <Row label="Rejected" value={verification?.rejected_at ? new Date(verification.rejected_at).toLocaleString() : null} />
          {verification?.rejection_reason && (
            <Row label="Rejection Reason" value={verification.rejection_reason} />
          )}
          {verification?.more_information_message && (
            <Row label="More Info Requested" value={verification.more_information_message} />
          )}
        </Section>

        <Section title="Audit Activity">
          {data.data.recent_audit_logs.length === 0 ? (
            <p className="text-on-surface-variant text-sm">No audit activity yet.</p>
          ) : (
            data.data.recent_audit_logs.map((log, index) => (
              <Row
                key={index}
                label={log.action.replaceAll("_", " ")}
                value={new Date(log.created_at).toLocaleString()}
              />
            ))
          )}
        </Section>
      </div>

      {canReview && (
        <div className="border-outline-variant/40 bg-surface-container-low rounded-lg border p-4">
          <h2 className="text-on-surface text-sm font-semibold">Review Decision</h2>

          {pendingAction && (
            <div className="mt-3">
              <textarea
                value={reasonText}
                onChange={(event) => setReasonText(event.target.value)}
                placeholder={
                  pendingAction === "reject"
                    ? "Reason for rejection…"
                    : "What additional information is needed?"
                }
                rows={3}
                className="border-outline-variant bg-surface-container-lowest text-on-surface w-full rounded-lg border px-3 py-2 text-sm focus:outline-none"
              />
            </div>
          )}

          {actionError && <p className="text-error mt-2 text-sm">{actionError}</p>}

          <div className="mt-4 flex flex-wrap gap-2">
            {!pendingAction && (
              <>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => runAction("/approve")}
                  className="bg-success/15 text-success rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-60"
                >
                  Approve
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => setPendingAction("more-info")}
                  className="bg-warning/15 text-warning rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-60"
                >
                  Request More Information
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => setPendingAction("reject")}
                  className="bg-error/15 text-error rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-60"
                >
                  Reject
                </button>
              </>
            )}
            {pendingAction && (
              <>
                <button
                  type="button"
                  disabled={submitting || reasonText.trim().length < 3}
                  onClick={() =>
                    pendingAction === "reject"
                      ? runAction("/reject", { reason: reasonText })
                      : runAction("/request-more-information", { message: reasonText })
                  }
                  className="bg-primary-container text-on-primary-container rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-60"
                >
                  {submitting ? "Submitting…" : "Confirm"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPendingAction(null);
                    setReasonText("");
                  }}
                  className="text-on-surface-variant rounded-lg px-4 py-2 text-sm font-semibold hover:underline"
                >
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <div className="border-outline-variant/40 bg-surface-container-low rounded-lg border p-4">
        <h2 className="text-on-surface text-sm font-semibold">Financial Access</h2>
        <p className="text-on-surface-variant mt-1 text-xs">
          Independent of approval status — enabling business access does not enable Collections
          or Payouts. Infinity Radius centrally manages both; tenants never configure
          payment-provider credentials.
        </p>
        <div className="mt-3 divide-y divide-outline-variant/30">
          <FlagToggle
            label="Collection Access"
            description="Allows this tenant's captive portal to accept customer payments."
            enabled={data.data.collection_enabled}
            disabled={submitting}
            onToggle={(next) => runAction("/collection", { enabled: next })}
          />
          <FlagToggle
            label="Payout Access"
            description="Allows this tenant to request payouts from their wallet."
            enabled={data.data.payout_enabled}
            disabled={submitting}
            onToggle={(next) => runAction("/payout", { enabled: next })}
          />
        </div>
      </div>

      {tenant.status === "ACTIVE" && (
        <div className="border-outline-variant/40 bg-surface-container-low rounded-lg border p-4">
          <button
            type="button"
            disabled={submitting}
            onClick={() => runAction("/suspend", { reason: null })}
            className="bg-error/15 text-error rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-60"
          >
            Suspend Tenant
          </button>
        </div>
      )}

      {tenant.status === "SUSPENDED" && (
        <div className="border-outline-variant/40 bg-surface-container-low rounded-lg border p-4">
          <button
            type="button"
            disabled={submitting}
            onClick={() => runAction("/reactivate")}
            className="bg-success/15 text-success rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-60"
          >
            Reactivate Tenant
          </button>
        </div>
      )}
    </div>
  );
}
