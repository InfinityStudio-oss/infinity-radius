"use client";

import { useEffect, useRef, useState } from "react";
import { apiMutate, ApiClientError } from "@/lib/api-client";
import { useAccessToken } from "@/lib/hooks/use-access-token";

// Mirrors app.core.enums.DestinationCode exactly — the backend is the
// canonical source; this list exists only so the tenant can pick a value
// the backend will actually accept, never a free-typed code.
const MOBILE_MONEY_CODES = ["MPESA", "AIRTELMONEY", "HALOPESA", "MIXXBYYAS", "TTCLPESA"] as const;
const BANK_CODES = [
  "CRDB",
  "NMB",
  "NBC",
  "ABSA",
  "KCB",
  "EQUITY",
  "EXIM",
  "STANBIC",
  "SCB",
  "NCBA",
  "DTB",
  "BOA",
  "AZANIA",
  "ECOBANK",
  "GTBANK",
  "UBA",
  "CITI",
] as const;

interface Destination {
  id: string;
  label: string;
  channel: string;
  destination_code: string | null;
  account_number: string | null;
  account_name: string | null;
  is_default: boolean;
}

interface LookupResult {
  account_name: string | null;
  operator: string | null;
  total_charges: string | null;
  approval_required: boolean;
}

interface WithdrawalResult {
  withdrawal: { id: string; status: string; approval_required: boolean };
  otp_sent: boolean;
  masked_email: string;
  expires_in_seconds: number;
}

interface OtpResendResult {
  otp_sent: boolean;
  masked_email: string;
  expires_in_seconds: number;
}

type Step = "destination" | "new-destination" | "amount" | "review" | "two-factor" | "done";

export interface WithdrawDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  destinations: Destination[];
  onCompleted: () => void;
}

export function WithdrawDialog({
  open,
  onOpenChange,
  destinations,
  onCompleted,
}: WithdrawDialogProps) {
  const { token } = useAccessToken();
  const [step, setStep] = useState<Step>("destination");
  const [destinationId, setDestinationId] = useState<string | null>(
    destinations.find((d) => d.is_default)?.id ?? destinations[0]?.id ?? null,
  );
  const [newLabel, setNewLabel] = useState("");
  const [newChannel, setNewChannel] = useState<"mobile_money" | "bank" | "selcom">(
    "mobile_money",
  );
  const [newCode, setNewCode] = useState<string>(MOBILE_MONEY_CODES[0]);
  const [newAccount, setNewAccount] = useState("");
  const [amount, setAmount] = useState("");
  const [lookup, setLookup] = useState<LookupResult | null>(null);
  const [withdrawal, setWithdrawal] = useState<WithdrawalResult | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);
  const cooldownTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Purely a UX countdown — the server is the real authority on the
  // cooldown (see POST /payouts/{id}/resend-otp, WITHDRAWAL_OTP_RESEND_
  // COOLDOWN_SECONDS). If it ever desyncs, a 429's message is parsed back
  // into this same counter (see resendOtp's catch block below).
  function startResendCooldown(seconds: number) {
    if (cooldownTimer.current) clearInterval(cooldownTimer.current);
    setResendCooldown(seconds);
    cooldownTimer.current = setInterval(() => {
      setResendCooldown((prev) => {
        if (prev <= 1) {
          if (cooldownTimer.current) clearInterval(cooldownTimer.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }

  useEffect(() => {
    return () => {
      if (cooldownTimer.current) clearInterval(cooldownTimer.current);
    };
  }, []);

  function reset() {
    setStep("destination");
    setAmount("");
    setLookup(null);
    setWithdrawal(null);
    setCode("");
    setError(null);
    setResendCooldown(0);
    if (cooldownTimer.current) clearInterval(cooldownTimer.current);
  }

  function close() {
    reset();
    onOpenChange(false);
  }

  async function createDestination() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiMutate<{ data: Destination }>("/api/v1/payouts/destinations", {
        accessToken: token,
        body: {
          label: newLabel || newCode,
          channel: newChannel,
          destination_code: newCode,
          account_number: newAccount,
          is_default: destinations.length === 0,
        },
      });
      destinations.push(response.data);
      setDestinationId(response.data.id);
      setStep("amount");
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Could not save destination");
    } finally {
      setBusy(false);
    }
  }

  async function runLookup() {
    if (!destinationId) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiMutate<{ data: LookupResult }>("/api/v1/payouts/lookup", {
        accessToken: token,
        body: { destination_id: destinationId, amount },
      });
      setLookup(response.data);
      setStep("review");
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Could not verify destination");
    } finally {
      setBusy(false);
    }
  }

  async function confirmWithdrawal() {
    if (!destinationId) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiMutate<WithdrawalResult>("/api/v1/payouts", {
        accessToken: token,
        body: { destination_id: destinationId, amount },
      });
      setWithdrawal(response);
      setCode("");
      startResendCooldown(60);
      setStep("two-factor");
      if (!response.otp_sent) {
        setError(
          "We couldn't deliver the verification email — use Resend once the cooldown ends.",
        );
      }
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Could not create withdrawal");
    } finally {
      setBusy(false);
    }
  }

  async function resendOtp() {
    if (!withdrawal || resendCooldown > 0) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiMutate<OtpResendResult>(
        `/api/v1/payouts/${withdrawal.withdrawal.id}/resend-otp`,
        { accessToken: token, body: {} },
      );
      setWithdrawal({ ...withdrawal, ...response });
      setCode("");
      startResendCooldown(60);
      if (!response.otp_sent) {
        setError("We couldn't deliver the verification email — try again shortly.");
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
        const retryAfter = /(\d+)\s*seconds?/.exec(err.message)?.[1];
        if (retryAfter) startResendCooldown(Number(retryAfter));
      } else {
        setError("Could not resend the verification code");
      }
    } finally {
      setBusy(false);
    }
  }

  async function cancelDuringOtp() {
    if (!withdrawal) return;
    setBusy(true);
    try {
      await apiMutate(`/api/v1/payouts/${withdrawal.withdrawal.id}/cancel`, {
        accessToken: token,
        body: { reason: "Cancelled during verification" },
      });
      onCompleted();
    } catch {
      // Best-effort — the dialog closes regardless; a stuck DRAFT
      // withdrawal is still visible/cancellable from the withdrawals list.
    } finally {
      setBusy(false);
      close();
    }
  }

  async function confirmTwoFactor() {
    if (!withdrawal) return;
    setBusy(true);
    setError(null);
    try {
      await apiMutate(`/api/v1/payouts/${withdrawal.withdrawal.id}/confirm-2fa`, {
        accessToken: token,
        body: { code },
      });
      setStep("done");
      onCompleted();
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Invalid code");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  const codeOptions = newChannel === "bank" ? BANK_CODES : MOBILE_MONEY_CODES;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={close}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="border-outline-variant/40 bg-surface-container-low w-full max-w-md rounded-xl border p-6 shadow-2xl"
      >
        <h2 className="text-on-surface text-lg font-semibold">Withdraw</h2>

        {error && (
          <p className="bg-danger/10 text-danger mt-3 rounded-lg px-3 py-2 text-sm">{error}</p>
        )}

        {step === "destination" && (
          <div className="mt-4 flex flex-col gap-3">
            {destinations.length > 0 && (
              <select
                className="bg-surface-container-high text-on-surface rounded-lg px-3 py-2 text-sm"
                value={destinationId ?? ""}
                onChange={(e) => setDestinationId(e.target.value)}
              >
                {destinations.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label} ({d.destination_code ?? d.channel} — {d.account_number})
                  </option>
                ))}
              </select>
            )}
            <button
              type="button"
              className="text-primary text-left text-sm font-medium hover:underline"
              onClick={() => setStep("new-destination")}
            >
              + Add a new destination
            </button>
            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={close}
                className="text-on-surface-variant rounded-lg px-4 py-2 text-sm"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!destinationId}
                onClick={() => setStep("amount")}
                className="bg-primary-container text-on-primary-container rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {step === "new-destination" && (
          <div className="mt-4 flex flex-col gap-3">
            <input
              placeholder="Label (e.g. Business M-Pesa)"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              className="bg-surface-container-high text-on-surface rounded-lg px-3 py-2 text-sm"
            />
            <select
              value={newChannel}
              onChange={(e) => {
                const channel = e.target.value as typeof newChannel;
                setNewChannel(channel);
                setNewCode(channel === "bank" ? BANK_CODES[0] : MOBILE_MONEY_CODES[0]);
              }}
              className="bg-surface-container-high text-on-surface rounded-lg px-3 py-2 text-sm"
            >
              <option value="mobile_money">Mobile Money</option>
              <option value="bank">Bank</option>
              <option value="selcom">Selcom</option>
            </select>
            <select
              value={newCode}
              onChange={(e) => setNewCode(e.target.value)}
              className="bg-surface-container-high text-on-surface rounded-lg px-3 py-2 text-sm"
            >
              {(newChannel === "selcom" ? ["SELCOM"] : codeOptions).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <input
              placeholder={newChannel === "bank" ? "Bank account number" : "Phone number"}
              value={newAccount}
              onChange={(e) => setNewAccount(e.target.value)}
              className="bg-surface-container-high text-on-surface rounded-lg px-3 py-2 text-sm"
            />
            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setStep("destination")}
                className="text-on-surface-variant rounded-lg px-4 py-2 text-sm"
              >
                Back
              </button>
              <button
                type="button"
                disabled={busy || !newAccount}
                onClick={createDestination}
                className="bg-primary-container text-on-primary-container rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
              >
                {busy ? "Saving…" : "Save destination"}
              </button>
            </div>
          </div>
        )}

        {step === "amount" && (
          <div className="mt-4 flex flex-col gap-3">
            <label className="text-on-surface-variant text-xs font-semibold uppercase">
              Amount (TZS)
            </label>
            <input
              type="number"
              min="1"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="bg-surface-container-high text-on-surface rounded-lg px-3 py-2 text-sm"
              placeholder="e.g. 75000"
            />
            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setStep("destination")}
                className="text-on-surface-variant rounded-lg px-4 py-2 text-sm"
              >
                Back
              </button>
              <button
                type="button"
                disabled={busy || !amount || Number(amount) <= 0}
                onClick={runLookup}
                className="bg-primary-container text-on-primary-container rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
              >
                {busy ? "Verifying…" : "Verify Destination"}
              </button>
            </div>
          </div>
        )}

        {step === "review" && lookup && (
          <div className="mt-4 flex flex-col gap-3 text-sm">
            <div className="bg-surface-container-high flex flex-col gap-1 rounded-lg p-3">
              <Row label="Amount" value={`TZS ${Number(amount).toLocaleString()}`} />
              <Row label="Verified Recipient" value={lookup.account_name ?? "Could not verify"} />
              <Row label="Operator" value={lookup.operator ?? "—"} />
              {lookup.total_charges && (
                <Row label="Provider Charges" value={`TZS ${lookup.total_charges}`} />
              )}
              <Row
                label="Approval"
                value={lookup.approval_required ? "Super Admin approval required" : "Not required"}
              />
            </div>
            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setStep("amount")}
                className="text-on-surface-variant rounded-lg px-4 py-2 text-sm"
              >
                Back
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={confirmWithdrawal}
                className="bg-primary-container text-on-primary-container rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
              >
                {busy ? "Submitting…" : "Confirm Withdrawal"}
              </button>
            </div>
          </div>
        )}

        {step === "two-factor" && withdrawal && (
          <div className="mt-4 flex flex-col gap-3">
            <p className="text-on-surface-variant text-sm">
              Verification code sent to <span className="font-medium">{withdrawal.masked_email}</span>.
              Enter it below to confirm this withdrawal. It expires in{" "}
              {Math.round(withdrawal.expires_in_seconds / 60)} minutes.
            </p>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              maxLength={6}
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="\d{6}"
              className="bg-surface-container-high text-on-surface rounded-lg px-3 py-2 text-center font-mono text-lg tracking-widest"
              placeholder="000000"
            />
            <button
              type="button"
              disabled={busy || resendCooldown > 0}
              onClick={resendOtp}
              className="text-primary text-left text-sm font-medium hover:underline disabled:text-on-surface-variant disabled:no-underline"
            >
              {resendCooldown > 0 ? `Resend code in ${resendCooldown}s` : "Resend code"}
            </button>
            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={cancelDuringOtp}
                className="text-on-surface-variant rounded-lg px-4 py-2 text-sm disabled:opacity-50"
              >
                Cancel Withdrawal
              </button>
              <button
                type="button"
                disabled={busy || code.length !== 6}
                onClick={confirmTwoFactor}
                className="bg-primary-container text-on-primary-container rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
              >
                {busy ? "Confirming…" : "Confirm Code"}
              </button>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="mt-4 flex flex-col gap-3">
            <p className="text-on-surface text-sm">
              {withdrawal?.withdrawal.approval_required
                ? "Withdrawal submitted — awaiting Super Admin approval."
                : "Withdrawal submitted — processing with the provider."}
            </p>
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={close}
                className="bg-primary-container text-on-primary-container rounded-lg px-4 py-2 text-sm font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-on-surface-variant">{label}</span>
      <span className="text-on-surface font-medium">{value}</span>
    </div>
  );
}
