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

interface PaymentInitiateResult {
  transaction_token: string;
  status: "pending" | "provider_not_configured";
  amount: string;
  currency: string;
}

interface PaymentStatusResult {
  status: "pending" | "completed" | "failed" | "not_found";
  login_username: string | null;
  login_password: string | null;
}

type Step = "select-package" | "enter-phone" | "waiting" | "success" | "failed" | "unavailable";

const POLL_INTERVAL_MS = 3000;

/** Loose client-side check only — normalize_tz_phone on the backend is the
 * real validator. 9 digits after the fixed +255, starting 6 or 7. */
function isPlausibleTzSubscriberNumber(digits: string): boolean {
  return /^[67]\d{8}$/.test(digits);
}

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
  const [loginCredentials, setLoginCredentials] = useState<{
    username: string;
    password: string;
  } | null>(null);
  const [unavailableReason, setUnavailableReason] = useState<string | null>(null);

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

  async function handleChoosePackage() {
    if (!selectedPackage) return;
    setStep("enter-phone");
  }

  async function handleSubmitPhone() {
    if (!routerToken || !selectedPackage) return;
    if (!isPlausibleTzSubscriberNumber(subscriberNumber)) {
      setPhoneError("Enter a valid Tanzanian mobile number (e.g. 712 345 678).");
      return;
    }
    setPhoneError(null);
    setSubmitting(true);
    try {
      const initiated = await apiMutate<PaymentInitiateResult>(
        "/api/v1/public/captive-portal/payments/initiate",
        {
          body: {
            router: routerToken,
            package_id: selectedPackage.id,
            phone: `255${subscriberNumber}`,
          },
        },
      );
      if (initiated.status === "provider_not_configured") {
        setUnavailableReason(
          "Online payment isn't available on this network yet. Please contact your network administrator.",
        );
        setStep("unavailable");
        return;
      }
      setTransactionToken(initiated.transaction_token);
      setStep("waiting");
    } catch (err) {
      setPhoneError(
        err instanceof ApiClientError ? err.message : "Could not start payment. Try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // Polls every 2-5s (here: 3s) — the initial, simplest-correct
  // implementation the payment-waiting screen needs. Stops as soon as a
  // terminal status (completed/failed) is reached.
  useEffect(() => {
    if (step !== "waiting" || !transactionToken) return;
    let cancelled = false;

    async function poll() {
      try {
        const result = await apiFetch<PaymentStatusResult>(
          `/api/v1/public/captive-portal/payments/status?token=${encodeURIComponent(transactionToken as string)}`,
        );
        if (cancelled) return;
        if (result.status === "completed") {
          if (result.login_username && result.login_password) {
            setLoginCredentials({
              username: result.login_username,
              password: result.login_password,
            });
          }
          setStep("success");
        } else if (result.status === "failed" || result.status === "not_found") {
          setStep("failed");
        }
      } catch {
        // Transient network error on a low-quality pre-auth connection —
        // just try again on the next tick, don't fail the whole flow.
      }
    }

    const interval = setInterval(poll, POLL_INTERVAL_MS);
    void poll();
    return () => {
      cancelled = true;
      clearInterval(interval);
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
                  We&apos;ll send a payment request to this number for{" "}
                  <MoneyDisplay amount={selectedPackage.price_tzs} currency="TZS" />.
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
                    onChange={(e) =>
                      setSubscriberNumber(e.target.value.replace(/\D/g, "").slice(0, 9))
                    }
                    placeholder="712 345 678"
                    className="text-on-surface placeholder:text-outline w-full bg-transparent font-mono text-sm tracking-wide focus:outline-none"
                  />
                </div>
                {phoneError && <p className="text-error text-xs font-medium">{phoneError}</p>}
                <button
                  type="button"
                  disabled={submitting || subscriberNumber.length < 9}
                  onClick={handleSubmitPhone}
                  className="from-primary-container to-tertiary-container text-on-primary-container flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r px-4 py-3 font-bold shadow-lg transition-all disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {submitting && <Loader2 size={16} className="animate-spin" />}
                  Pay &amp; Connect
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

            {step === "waiting" && (
              <section className="relative z-10 flex flex-col items-center gap-3 py-6 text-center">
                <Loader2 size={36} className="text-primary animate-spin" />
                <h2 className="text-on-surface text-lg font-semibold">
                  Waiting for payment confirmation
                </h2>
                <p className="text-on-surface-variant text-sm">
                  Check your phone and approve the payment prompt. This page will update
                  automatically.
                </p>
              </section>
            )}

            {step === "success" && (
              <section className="relative z-10 flex flex-col items-center gap-3 py-6 text-center">
                <CheckCircle2 size={40} className="text-secondary" />
                <h2 className="text-on-surface text-lg font-semibold">You&apos;re connected!</h2>
                <p className="text-on-surface-variant text-sm">
                  {loginUrl
                    ? "Finishing your connection…"
                    : "Payment confirmed. Reconnect to the WiFi to go online."}
                </p>
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

            {step === "failed" && (
              <section className="relative z-10 flex flex-col items-center gap-3 py-6 text-center">
                <XCircle size={40} className="text-error" />
                <h2 className="text-on-surface text-lg font-semibold">Payment not completed</h2>
                <p className="text-on-surface-variant text-sm">
                  The payment wasn&apos;t confirmed. You haven&apos;t been charged for a plan you
                  didn&apos;t get.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setStep("select-package");
                    setTransactionToken(null);
                  }}
                  className="bg-surface-container-high text-on-surface rounded-lg px-4 py-2.5 text-sm font-semibold"
                >
                  Try again
                </button>
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
