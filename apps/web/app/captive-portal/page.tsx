"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2, ShieldCheck, WifiOff, XCircle, Zap } from "lucide-react";
import { Logo, MoneyDisplay, RealtimeIndicator } from "@infinity-radius/ui";
import {
  PackageSelector,
  type CaptivePortalPackage,
} from "@/components/captive-portal/package-selector";
import { usePublicApiQuery } from "@/lib/hooks/use-public-api-query";
import { apiFetch, apiMutate, ApiClientError } from "@/lib/api-client";
import {
  canRetryPayment,
  formatDuration,
  formatTzs,
  isPlausibleTzSubscriberNumber,
  isTerminalState,
  pollIntervalMs,
  sanitizeSubscriberInput,
  screenStateFor,
  type PaymentInitiateResult,
  type PaymentStatusResult,
  type ScreenState,
} from "@/lib/captive-portal/flow";

/** Mirrors apps/api/app/schemas/captive_portal.py — keep in sync by hand. */
interface CaptivePortalResolveResult {
  status: "ok" | "invalid_token" | "router_not_found";
  router_name: string | null;
  site_name: string | null;
  mac: string | null;
  dst: string | null;
  login_url: string | null;
}

interface CaptivePortalBranding {
  tenant_name: string;
  logo_url: string | null;
  brand_color: string | null;
}

/** Confirmation is a deliberate, separate step: a customer must see the
 *  package, the price and the validity they are about to pay for before
 *  anything reaches their handset. */
type Step =
  | "select-package"
  | "enter-phone"
  | "confirm"
  | "waiting"
  | "unavailable";

/** True only for an absolute http(s) URL — never used otherwise, so a
 * malformed `dst` from a hotspot's own query string can't smuggle
 * anything unexpected into the final redirect. */
function isSafeAbsoluteUrl(value: string | null): value is string {
  if (!value) return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function CaptivePortalContent() {
  const searchParams = useSearchParams();
  // The ONLY context a hotspot redirect carries: a signed router token,
  // the client's MAC, the originally-requested destination, and the
  // router's own local login endpoint — never a tenant id or anything
  // else. See apps/api/app/core/router_token.py.
  const routerToken = searchParams.get("router");
  const mac = searchParams.get("mac");
  const dst = searchParams.get("dst");

  const [step, setStep] = useState<Step>("select-package");
  const [selectedPackage, setSelectedPackage] = useState<CaptivePortalPackage | null>(null);
  const [subscriberNumber, setSubscriberNumber] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [transactionToken, setTransactionToken] = useState<string | null>(null);
  const [statusResult, setStatusResult] = useState<PaymentStatusResult | null>(null);
  const [unavailableReason, setUnavailableReason] = useState<string | null>(null);
  /** Secondary UX guard only. The real duplicate protection is server-side
   *  (one live attempt per session/package/phone) — a frontend lock cannot
   *  be the security boundary. */
  const submittedRef = useRef(false);

  const screen: ScreenState | null = statusResult ? screenStateFor(statusResult) : null;
  const loginCredentials =
    statusResult?.login_username && statusResult?.login_password
      ? { username: statusResult.login_username, password: statusResult.login_password }
      : null;

  const resolvePath = routerToken
    ? `/api/v1/public/captive-portal/resolve?router=${encodeURIComponent(routerToken)}${
        mac ? `&mac=${encodeURIComponent(mac)}` : ""
      }${dst ? `&dst=${encodeURIComponent(dst)}` : ""}`
    : null;
  const { data: resolved } = usePublicApiQuery<CaptivePortalResolveResult>(resolvePath);

  const brandingPath = routerToken
    ? `/api/v1/public/captive-portal/branding?router=${encodeURIComponent(routerToken)}`
    : null;
  const { data: branding } = usePublicApiQuery<CaptivePortalBranding>(brandingPath);

  const portalReady = resolved?.status === "ok";
  const siteName = resolved?.site_name ?? resolved?.router_name ?? null;
  const loginUrl = resolved?.login_url ?? null;

  function handleChoosePackage() {
    if (!selectedPackage) return;
    setStep("enter-phone");
  }

  function handleConfirmPhone() {
    if (!isPlausibleTzSubscriberNumber(subscriberNumber)) {
      setPhoneError("Enter a valid Tanzanian mobile number (e.g. 712 345 678).");
      return;
    }
    setPhoneError(null);
    setStep("confirm");
  }

  /** The one deliberate "spend my money" action in the whole flow. */
  async function handlePay() {
    if (!routerToken || !selectedPackage) return;
    if (submittedRef.current) return; // double-click guard (UX only)
    submittedRef.current = true;
    setSubmitting(true);
    try {
      // A fresh single-use session per attempt. The router token cannot
      // authorize a payment on its own — see the backend's captive intent
      // token.
      const session = await apiMutate<{ intent_token: string }>(
        "/api/v1/public/captive-portal/session",
        { body: { router: routerToken, mac_address: mac ?? undefined } },
      );

      const initiated = await apiMutate<PaymentInitiateResult>(
        "/api/v1/public/captive-portal/payments/initiate",
        {
          body: {
            intent_token: session.intent_token,
            package_id: selectedPackage.id,
            // Server normalizes authoritatively; this prefix is UX only.
            phone: `255${subscriberNumber}`,
          },
        },
      );

      if (initiated.status === "unavailable" || initiated.status === "provider_not_configured") {
        setUnavailableReason(
          initiated.message ??
            "Online payment is not available on this network yet. Please contact your network administrator.",
        );
        setStep("unavailable");
        return;
      }
      if (initiated.status === "rate_limited") {
        setUnavailableReason(
          initiated.message ?? "Too many payment attempts. Please wait a few minutes and try again.",
        );
        setStep("unavailable");
        return;
      }
      // "duplicate" is a success path: the server handed back the attempt
      // already in flight rather than sending a second prompt.
      setTransactionToken(initiated.transaction_token);
      setStep("waiting");
    } catch (err) {
      submittedRef.current = false;
      setPhoneError(
        err instanceof ApiClientError ? err.message : "Could not start payment. Try again.",
      );
      setStep("enter-phone");
    } finally {
      setSubmitting(false);
    }
  }

  /** Only reachable from a genuinely failed payment — see canRetryPayment. */
  function handleDeliberateRetry() {
    submittedRef.current = false;
    setTransactionToken(null);
    setStatusResult(null);
    setStep("select-package");
  }

  // Polls with backoff: responsive at first (most STK approvals land in
  // seconds), then slower, so a customer who walks away does not leave a
  // tab hammering the API. Stops only once there is genuinely nothing
  // left to learn — an under-review payment keeps being watched, because
  // it can still settle.
  useEffect(() => {
    if (step !== "waiting" || !transactionToken) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    async function poll() {
      attempt += 1;
      try {
        const result = await apiFetch<PaymentStatusResult>(
          `/api/v1/public/captive-portal/payments/status?token=${encodeURIComponent(
            transactionToken as string,
          )}`,
        );
        if (cancelled) return;
        setStatusResult(result);
        if (isTerminalState(screenStateFor(result))) return;
      } catch {
        // Transient network error on a low-quality pre-auth connection —
        // try again on the next tick rather than failing the whole flow.
      }
      if (!cancelled) timer = setTimeout(poll, pollIntervalMs(attempt));
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [step, transactionToken]);

  return (
    <>
      <header className="bg-surface/80 fixed top-0 z-50 w-full pt-[env(safe-area-inset-top,0px)] shadow-[0_1px_8px_rgba(0,0,0,0.25)] backdrop-blur-xl">
        <div className="flex flex-col gap-1 px-4 py-3">
          <div className="flex items-center justify-between">
            {branding?.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- external tenant-hosted logo, no build-time optimization possible
              <img src={branding.logo_url} alt={branding.tenant_name} className="h-7 w-auto" />
            ) : (
              <Logo markClassName="h-7 w-7" wordmarkClassName="text-base" />
            )}
          </div>
          <RealtimeIndicator
            connected={portalReady}
            label={siteName ?? "Hotspot Login"}
            offlineLabel={routerToken ? "Network not linked" : "No network detected"}
          />
        </div>
      </header>

      <main className="z-10 flex w-full flex-col px-4 pb-24 pt-24">
        <div className="mx-auto flex w-full max-w-lg flex-col gap-4">
          <div className="bg-surface-container-lowest relative flex flex-col gap-4 overflow-hidden rounded-xl p-4 shadow-2xl">
            <div className="bg-tertiary-container/20 pointer-events-none absolute -right-20 -top-24 h-48 w-48 rounded-full blur-3xl" />

            <div className="relative z-10 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                {branding?.logo_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={branding.logo_url}
                    alt={branding.tenant_name}
                    className="h-10 w-auto"
                  />
                ) : (
                  <Logo markClassName="h-10 w-10" wordmarkClassName="text-lg" />
                )}
                <span className="bg-surface-container-high inline-flex items-center gap-1.5 rounded-full px-2 py-1">
                  <span
                    className={`h-2 w-2 rounded-full ${portalReady ? "bg-secondary animate-pulse" : "bg-outline"}`}
                  />
                  <span className="text-secondary font-mono text-[0.6875rem] font-semibold">
                    {portalReady ? "Portal Ready" : "Connecting…"}
                  </span>
                </span>
              </div>

              <div>
                <h1 className="text-on-surface text-2xl font-extrabold tracking-tight">
                  Connect to WiFi
                </h1>
                <p className="text-on-surface-variant mt-1 text-sm">
                  {branding?.tenant_name ? `${branding.tenant_name} — ` : ""}
                  Select a plan and pay instantly to get online.
                </p>
              </div>

              {/* Site name is shown only when the backend actually
                  resolved this router — never a fabricated SSID or
                  signal-strength indicator. */}
              <div className="bg-surface-container-low flex items-center justify-between rounded-lg p-2 shadow-sm">
                <div className="flex min-w-0 items-center gap-2">
                  {siteName ? (
                    <span className="text-on-surface truncate font-mono text-[0.6875rem] font-semibold">
                      Site: {siteName}
                    </span>
                  ) : (
                    <span className="text-on-surface-variant flex items-center gap-1 font-mono text-[0.6875rem]">
                      <WifiOff size={14} /> Site unavailable
                    </span>
                  )}
                </div>
              </div>
            </div>

            {step === "select-package" && (
              <>
                <section className="relative z-10 flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className="bg-primary-container text-on-primary-container flex h-5 w-5 items-center justify-center rounded-full font-mono text-[0.6875rem] font-bold">
                        1
                      </span>
                      <h2 className="text-on-surface text-lg font-semibold">Select Access Plan</h2>
                    </div>
                    <span className="bg-surface-container-high text-secondary flex items-center gap-1 rounded-full px-2 py-0.5">
                      <Zap size={12} />
                      <span className="font-sans text-[0.6875rem] font-bold uppercase tracking-wide">
                        Instant
                      </span>
                    </span>
                  </div>

                  <PackageSelector
                    routerToken={routerToken}
                    selectedId={selectedPackage?.id ?? null}
                    onSelect={setSelectedPackage}
                  />
                </section>

                <button
                  type="button"
                  disabled={!selectedPackage}
                  onClick={handleChoosePackage}
                  className="from-primary-container to-tertiary-container text-on-primary-container relative z-10 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r px-4 py-3 font-bold shadow-lg transition-all disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {selectedPackage ? (
                    <>
                      Continue with <MoneyDisplay amount={selectedPackage.price_tzs} currency="TZS" />
                    </>
                  ) : (
                    "Select a plan to continue"
                  )}
                </button>
              </>
            )}

            {step === "enter-phone" && selectedPackage && (
              <section className="relative z-10 flex flex-col gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="bg-primary-container text-on-primary-container flex h-5 w-5 items-center justify-center rounded-full font-mono text-[0.6875rem] font-bold">
                    2
                  </span>
                  <h2 className="text-on-surface text-lg font-semibold">Your mobile number</h2>
                </div>
                <p className="text-on-surface-variant text-sm">
                  We&apos;ll send a payment request to this number.
                </p>
                <div className="bg-surface-container-low focus-within:ring-primary flex items-center gap-2 rounded-lg px-3 py-3 focus-within:ring-1">
                  <span className="text-on-surface-variant font-mono text-sm font-semibold">
                    +255
                  </span>
                  <input
                    inputMode="numeric"
                    autoComplete="tel-national"
                    maxLength={9}
                    value={subscriberNumber}
                    onChange={(e) => setSubscriberNumber(sanitizeSubscriberInput(e.target.value))}
                    placeholder="712 345 678"
                    aria-label="Mobile number"
                    className="text-on-surface placeholder:text-outline w-full bg-transparent font-mono text-sm tracking-wide focus:outline-none"
                  />
                </div>
                {phoneError && <p className="text-error text-xs font-medium">{phoneError}</p>}
                <button
                  type="button"
                  disabled={subscriberNumber.length < 9}
                  onClick={handleConfirmPhone}
                  className="from-primary-container to-tertiary-container text-on-primary-container flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r px-4 py-3 font-bold shadow-lg transition-all disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Review payment
                </button>
                <button
                  type="button"
                  onClick={() => setStep("select-package")}
                  className="text-on-surface-variant text-center text-xs font-medium"
                >
                  Back to plans
                </button>
              </section>
            )}

            {/* Deliberate confirmation. Nothing reaches the customer's
                handset until they have seen exactly what they are buying,
                for how long, and at what price. */}
            {step === "confirm" && selectedPackage && (
              <section className="relative z-10 flex flex-col gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="bg-primary-container text-on-primary-container flex h-5 w-5 items-center justify-center rounded-full font-mono text-[0.6875rem] font-bold">
                    3
                  </span>
                  <h2 className="text-on-surface text-lg font-semibold">Confirm your purchase</h2>
                </div>

                <dl className="bg-surface-container-low flex flex-col gap-2 rounded-lg p-3">
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-on-surface-variant text-sm">Plan</dt>
                    <dd className="text-on-surface text-sm font-semibold">
                      {selectedPackage.name}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-on-surface-variant text-sm">Valid for</dt>
                    <dd className="text-on-surface text-sm font-semibold">
                      {formatDuration(selectedPackage.duration_minutes)}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-on-surface-variant text-sm">Mobile number</dt>
                    <dd className="text-on-surface font-mono text-sm font-semibold">
                      +255 {subscriberNumber}
                    </dd>
                  </div>
                  <div className="border-outline-variant/40 mt-1 flex items-center justify-between gap-3 border-t pt-2">
                    <dt className="text-on-surface text-base font-semibold">Total</dt>
                    <dd className="text-on-surface text-lg font-extrabold">
                      TZS {formatTzs(selectedPackage.price_tzs)}
                    </dd>
                  </div>
                </dl>

                <p className="text-on-surface-variant text-xs">
                  You&apos;ll get a prompt on your phone. Enter your mobile money PIN to complete
                  the payment.
                </p>

                <button
                  type="button"
                  disabled={submitting}
                  onClick={handlePay}
                  className="from-primary-container to-tertiary-container text-on-primary-container flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r px-4 py-3 font-bold shadow-lg transition-all disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {submitting && <Loader2 size={16} className="animate-spin" />}
                  Pay with Mobile Money
                </button>
                <button
                  type="button"
                  onClick={() => setStep("enter-phone")}
                  className="text-on-surface-variant text-center text-xs font-medium"
                >
                  Change number
                </button>
              </section>
            )}

            {step === "waiting" && screen !== "active" && screen !== "failed" && (
              <section className="relative z-10 flex flex-col items-center gap-3 py-6 text-center">
                {screen === "under-review" ? (
                  <>
                    {/* The most important screen in the flow. This payment
                        may still settle, so the customer must NOT be told
                        it failed and must NOT be offered a retry — paying
                        again on top of one that later succeeds is a real
                        double charge. */}
                    <ShieldCheck size={40} className="text-tertiary" />
                    <h2 className="text-on-surface text-lg font-semibold">
                      Still confirming your payment
                    </h2>
                    <p className="text-on-surface-variant text-sm">
                      {statusResult?.message ??
                        "We are still confirming your payment with your mobile money provider."}
                    </p>
                    <p className="bg-error-container/30 text-on-surface rounded-lg px-3 py-2 text-sm font-semibold">
                      Please do NOT pay again. If money left your account it will be applied to
                      this purchase.
                    </p>
                  </>
                ) : screen === "activating" ? (
                  <>
                    <Loader2 size={36} className="text-secondary animate-spin" />
                    <h2 className="text-on-surface text-lg font-semibold">Payment confirmed</h2>
                    <p className="text-on-surface-variant text-sm">
                      Setting up your internet access — this only takes a moment.
                    </p>
                  </>
                ) : screen === "activation-failed" ? (
                  <>
                    <ShieldCheck size={40} className="text-tertiary" />
                    <h2 className="text-on-surface text-lg font-semibold">Payment received</h2>
                    <p className="text-on-surface-variant text-sm">
                      {statusResult?.message ??
                        "We could not finish setting up your access automatically."}
                    </p>
                    <p className="text-on-surface-variant text-xs">
                      Our team has been notified. You have <strong>not</strong> been charged twice
                      — please contact your network administrator if access does not start
                      shortly.
                    </p>
                  </>
                ) : (
                  <>
                    <Loader2 size={36} className="text-primary animate-spin" />
                    <h2 className="text-on-surface text-lg font-semibold">
                      Waiting for payment confirmation
                    </h2>
                    <p className="text-on-surface-variant text-sm">
                      Check your phone and approve the payment prompt. This page will update
                      automatically.
                    </p>
                  </>
                )}
                {statusResult?.package_name && (
                  <p className="text-on-surface-variant font-mono text-[0.6875rem]">
                    {statusResult.package_name} · TZS {formatTzs(statusResult.amount)}
                    {statusResult.payer_phone_masked ? ` · ${statusResult.payer_phone_masked}` : ""}
                  </p>
                )}
              </section>
            )}

            {step === "waiting" && screen === "active" && (
              <section className="relative z-10 flex flex-col items-center gap-3 py-6 text-center">
                <CheckCircle2 size={40} className="text-secondary" />
                <h2 className="text-on-surface text-lg font-semibold">You&apos;re connected!</h2>
                <p className="text-on-surface-variant text-sm">
                  {loginUrl
                    ? "Finishing your connection…"
                    : "Payment confirmed. Reconnect to the WiFi to go online."}
                </p>
                {statusResult?.provider_reference && (
                  <p className="text-on-surface-variant font-mono text-[0.6875rem]">
                    Receipt: {statusResult.provider_reference}
                  </p>
                )}
                {loginUrl && loginCredentials && (
                  <LoginRedirectForm
                    loginUrl={loginUrl}
                    username={loginCredentials.username}
                    password={loginCredentials.password}
                    dst={isSafeAbsoluteUrl(dst) ? dst : null}
                  />
                )}
              </section>
            )}

            {step === "waiting" && screen === "failed" && (
              <section className="relative z-10 flex flex-col items-center gap-3 py-6 text-center">
                <XCircle size={40} className="text-error" />
                <h2 className="text-on-surface text-lg font-semibold">Payment not completed</h2>
                <p className="text-on-surface-variant text-sm">
                  {statusResult?.message ??
                    "The payment wasn't confirmed. You haven't been charged for a plan you didn't get."}
                </p>
                {/* A new attempt is deliberate and creates a NEW order — it
                    never resends the previous provider request. */}
                {screen && canRetryPayment(screen) && (
                  <button
                    type="button"
                    onClick={handleDeliberateRetry}
                    className="bg-surface-container-high text-on-surface rounded-lg px-4 py-2.5 text-sm font-semibold"
                  >
                    Try again
                  </button>
                )}
              </section>
            )}

            {step === "unavailable" && (
              <section className="relative z-10 flex flex-col items-center gap-3 py-6 text-center">
                <XCircle size={40} className="text-error" />
                <h2 className="text-on-surface text-lg font-semibold">Payment unavailable</h2>
                <p className="text-on-surface-variant text-sm">{unavailableReason}</p>
              </section>
            )}

            <div className="border-outline-variant/30 text-on-surface-variant relative z-10 flex items-center justify-center gap-4 border-t pt-3">
              <span className="flex items-center gap-1 text-xs">
                <ShieldCheck size={14} className="text-secondary" /> Encrypted Connection
              </span>
            </div>
          </div>

          <p className="text-on-surface-variant text-center text-xs">
            Need help? Contact your network administrator.
          </p>
        </div>
      </main>
    </>
  );
}

/**
 * Completes the router login/re-authentication flow (step 12-13): submits
 * a real (invisible) HTML form POST to the router's own local login
 * endpoint — a cross-origin browser navigation, not a fetch, since the
 * router needs to actually process this as a hotspot login request and
 * then redirect the browser onward to `dst` itself. Auto-submits once, on
 * mount.
 */
function LoginRedirectForm({
  loginUrl,
  username,
  password,
  dst,
}: {
  loginUrl: string;
  username: string;
  password: string;
  dst: string | null;
}) {
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    formRef.current?.submit();
  }, []);

  return (
    <form ref={formRef} method="post" action={loginUrl} className="hidden">
      <input type="hidden" name="username" value={username} />
      <input type="hidden" name="password" value={password} />
      {dst && <input type="hidden" name="dst" value={dst} />}
    </form>
  );
}

/** WiFi captive portal login page, served after a customer associates with a MikroTik AP. */
export default function CaptivePortalPage() {
  return (
    <Suspense fallback={null}>
      <CaptivePortalContent />
    </Suspense>
  );
}
