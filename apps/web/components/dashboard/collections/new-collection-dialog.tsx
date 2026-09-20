"use client";

import { useEffect, useRef, useState } from "react";
import { formatMoney } from "@infinity-radius/ui";
import { apiFetch, apiMutate, ApiClientError } from "@/lib/api-client";
import { useAccessToken } from "@/lib/hooks/use-access-token";
import { normalizeAmount } from "@/lib/collections/amount";
import { normalizeTzPhone } from "@/lib/collections/phone";
import { presentCollectionStatus } from "@/lib/collections/status";
import type { ApiEnvelope, TransactionRead } from "@/lib/api-types";
import { CollectionStatusBadge } from "./collection-status-badge";

type Step = "form" | "confirm" | "tracking";

export interface NewCollectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called once a request was actually created, so the list can refresh. */
  onCreated: () => void;
}

/**
 * Request-payment flow: enter details -> explicitly confirm -> one single
 * POST -> track the resulting transaction.
 *
 * Duplicate protection is the point of the confirm step and of `busy`:
 * exactly one POST /api/v1/collections is ever issued per dialog session.
 * There is deliberately no retry-on-failure and no "resend STK" action —
 * a failed or slow request is never automatically re-sent, because a
 * duplicate request would mean a duplicate charge to a real customer. A
 * new attempt is always a deliberate, fresh dialog session.
 */
export function NewCollectionDialog({
  open,
  onOpenChange,
  onCreated,
}: NewCollectionDialogProps) {
  const { token } = useAccessToken();
  const [step, setStep] = useState<Step>("form");
  const [phone, setPhone] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<TransactionRead | null>(null);

  /** Guards against a double-submit racing past the `busy` state update. */
  const submittedRef = useRef(false);

  const normalizedPhone = normalizeTzPhone(phone);
  const normalizedAmount = normalizeAmount(amount);

  function reset() {
    setStep("form");
    setPhone("");
    setAmount("");
    setDescription("");
    setFieldError(null);
    setError(null);
    setBusy(false);
    setCreated(null);
    submittedRef.current = false;
  }

  function close() {
    reset();
    onOpenChange(false);
  }

  function goToConfirm() {
    if (!normalizedPhone.ok) {
      setFieldError(normalizedPhone.reason);
      return;
    }
    if (!normalizedAmount.ok) {
      setFieldError(normalizedAmount.reason);
      return;
    }
    setFieldError(null);
    setStep("confirm");
  }

  async function submit() {
    // Two independent guards: the ref blocks a second call within the same
    // tick (before React has re-rendered with busy=true), `busy` blocks
    // everything after.
    if (submittedRef.current || busy) return;
    if (!normalizedPhone.ok || !normalizedAmount.ok) return;

    submittedRef.current = true;
    setBusy(true);
    setError(null);

    try {
      const response = await apiMutate<ApiEnvelope<TransactionRead>>("/api/v1/collections", {
        accessToken: token,
        body: {
          amount: normalizedAmount.value,
          currency: "TZS",
          phone: normalizedPhone.value,
          ...(description.trim() ? { description: description.trim() } : {}),
        },
      });
      setCreated(response.data);
      setStep("tracking");
      onCreated();
    } catch (err) {
      // Never auto-retry: a retry could mean a second real charge.
      const status = err instanceof ApiClientError ? err.status : undefined;
      if (status === 422) {
        // Covers the kill-switch/domain-validation responses. The backend's
        // message names an environment variable, which a tenant must never
        // see, so anything the gate rejects gets generic operator-safe copy.
        setError(
          "Collection requests are temporarily unavailable. Please try again later or contact support.",
        );
      } else {
        setError("Could not create the payment request. Please try again or contact support.");
      }
      setStep("form");
      submittedRef.current = false;
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-collection-title"
    >
      <div className="bg-surface-container-low max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-2xl p-5 sm:rounded-2xl sm:p-6">
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id="new-collection-title" className="text-on-surface text-lg font-semibold">
            {step === "tracking" ? "Payment request" : "Request payment"}
          </h2>
          <button
            type="button"
            onClick={close}
            className="text-on-surface-variant hover:text-on-surface text-sm"
            aria-label="Close"
          >
            Close
          </button>
        </div>

        {step === "form" && (
          <FormStep
            phone={phone}
            amount={amount}
            description={description}
            fieldError={fieldError}
            error={error}
            onPhone={setPhone}
            onAmount={setAmount}
            onDescription={setDescription}
            onContinue={goToConfirm}
          />
        )}

        {step === "confirm" && normalizedPhone.ok && normalizedAmount.ok && (
          <ConfirmStep
            phone={normalizedPhone.value}
            amount={normalizedAmount.value}
            busy={busy}
            onBack={() => setStep("form")}
            onConfirm={submit}
          />
        )}

        {step === "tracking" && created && (
          <TrackingStep transaction={created} onClose={close} />
        )}
      </div>
    </div>
  );
}

function FormStep({
  phone,
  amount,
  description,
  fieldError,
  error,
  onPhone,
  onAmount,
  onDescription,
  onContinue,
}: {
  phone: string;
  amount: string;
  description: string;
  fieldError: string | null;
  error: string | null;
  onPhone: (v: string) => void;
  onAmount: (v: string) => void;
  onDescription: (v: string) => void;
  onContinue: () => void;
}) {
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onContinue();
      }}
    >
      <div className="flex flex-col gap-1.5">
        <label htmlFor="collection-phone" className="text-on-surface text-sm font-medium">
          Customer phone number
        </label>
        <input
          id="collection-phone"
          name="phone"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          value={phone}
          onChange={(e) => onPhone(e.target.value)}
          placeholder="0762474101"
          className="border-outline bg-surface text-on-surface focus:border-primary rounded-lg border px-3 py-2 text-sm outline-none"
        />
        <p className="text-on-surface-variant text-xs">
          Accepts 07…, +255… or 255… formats.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="collection-amount" className="text-on-surface text-sm font-medium">
          Amount (TZS)
        </label>
        <input
          id="collection-amount"
          name="amount"
          type="text"
          inputMode="decimal"
          value={amount}
          onChange={(e) => onAmount(e.target.value)}
          placeholder="1000"
          className="border-outline bg-surface text-on-surface focus:border-primary rounded-lg border px-3 py-2 text-sm outline-none"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="collection-description" className="text-on-surface text-sm font-medium">
          Description <span className="text-on-surface-variant">(optional)</span>
        </label>
        <input
          id="collection-description"
          name="description"
          type="text"
          value={description}
          onChange={(e) => onDescription(e.target.value)}
          placeholder="What is this payment for?"
          className="border-outline bg-surface text-on-surface focus:border-primary rounded-lg border px-3 py-2 text-sm outline-none"
        />
      </div>

      {fieldError && (
        <p role="alert" className="text-danger text-sm">
          {fieldError}
        </p>
      )}
      {error && (
        <p role="alert" className="text-danger text-sm">
          {error}
        </p>
      )}

      <button
        type="submit"
        className="bg-primary text-on-primary rounded-lg px-4 py-2.5 text-sm font-semibold"
      >
        Continue
      </button>
    </form>
  );
}

function ConfirmStep({
  phone,
  amount,
  busy,
  onBack,
  onConfirm,
}: {
  phone: string;
  amount: string;
  busy: boolean;
  onBack: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-on-surface text-sm">
        An STK payment request for{" "}
        <strong className="font-semibold">{formatMoney(amount) ?? `TZS ${amount}`}</strong> will
        be sent to <strong className="font-semibold">{phone}</strong>.
      </p>
      <p className="text-on-surface-variant text-sm">
        The customer approves it on their phone. Only send this once — sending again would ask
        the customer to pay twice.
      </p>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={onBack}
          disabled={busy}
          className="border-outline text-on-surface rounded-lg border px-4 py-2.5 text-sm font-medium disabled:opacity-50"
        >
          Back
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className="bg-primary text-on-primary rounded-lg px-4 py-2.5 text-sm font-semibold disabled:opacity-60"
        >
          {busy ? "Sending…" : "Send payment request"}
        </button>
      </div>
    </div>
  );
}

function TrackingStep({
  transaction,
  onClose,
}: {
  transaction: TransactionRead;
  onClose: () => void;
}) {
  const live = useCollectionPolling(transaction);
  const presentation = presentCollectionStatus(live.status);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-on-surface text-2xl font-semibold">
          {formatMoney(live.amount) ?? `TZS ${live.amount}`}
        </span>
        <CollectionStatusBadge status={live.status} />
      </div>

      <p className="text-on-surface-variant text-sm">{presentation.message}</p>

      <dl className="flex flex-col gap-2 text-sm">
        <div className="flex justify-between gap-4">
          <dt className="text-on-surface-variant">Customer</dt>
          <dd className="text-on-surface font-mono">{live.payer_phone_masked ?? "—"}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-on-surface-variant">Infinity Radius Order ID</dt>
          <dd className="text-on-surface break-all font-mono text-xs">{live.reference}</dd>
        </div>
        {presentation.isPaid && live.provider_reference && (
          <div className="flex justify-between gap-4">
            <dt className="text-on-surface-variant">Mobile Money Reference</dt>
            <dd className="text-on-surface font-mono text-xs">{live.provider_reference}</dd>
          </div>
        )}
      </dl>

      <button
        type="button"
        onClick={onClose}
        className="bg-primary text-on-primary rounded-lg px-4 py-2.5 text-sm font-semibold"
      >
        Done
      </button>
    </div>
  );
}

/**
 * Polls this one transaction's local state while it is non-terminal.
 *
 * Reads Infinity Radius only — the browser never contacts Selcom, and this
 * never asks the backend to re-query the provider. Backend worker
 * reconciliation is what actually advances the status; this just observes
 * it. Polling stops as soon as the status is terminal and is cleaned up on
 * unmount.
 */
function useCollectionPolling(initial: TransactionRead): TransactionRead {
  const { token } = useAccessToken();
  const [transaction, setTransaction] = useState(initial);

  useEffect(() => {
    if (!presentCollectionStatus(transaction.status).isPolling) return;

    let active = true;
    const controller = new AbortController();
    const timer = setInterval(() => {
      apiFetch<ApiEnvelope<TransactionRead>>(`/api/v1/collections/${transaction.id}`, {
        accessToken: token,
        signal: controller.signal,
      })
        .then((response) => {
          if (active) setTransaction(response.data);
        })
        .catch(() => {
          /* transient read failure — the next tick retries */
        });
    }, 5000);

    return () => {
      active = false;
      controller.abort();
      clearInterval(timer);
    };
  }, [transaction.id, transaction.status, token]);

  return transaction;
}
