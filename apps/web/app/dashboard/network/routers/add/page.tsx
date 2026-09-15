"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronRight, Loader2 } from "lucide-react";
import { PageHeader } from "@infinity-radius/ui";
import { apiFetch, apiMutate, ApiClientError } from "@/lib/api-client";
import { useAccessToken } from "@/lib/hooks/use-access-token";
import { CopyBlock } from "@/components/dashboard/router-wizard/copy-block";
import type {
  ApiEnvelope,
  HotspotConfigResult,
  Location,
  NetworkConfigRead,
  PublicRouterTokenResult,
  RadiusConfigResult,
  RouterRead,
  TestConnectionResult,
  WalledGardenResult,
  WireGuardConfigResult,
} from "@/components/dashboard/router-wizard/types";

const STEP_LABELS = [
  "Router identity",
  "Hotspot site",
  "Network config",
  "WireGuard",
  "RADIUS",
  "Hotspot config",
  "Walled garden",
  "Connectivity test",
  "Save router",
] as const;

const inputClass =
  "bg-surface-container-low text-on-surface placeholder:text-on-surface-variant/60 focus:ring-primary rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1";
const labelClass = "text-on-surface-variant text-xs font-semibold uppercase tracking-wide";
const primaryButtonClass =
  "bg-primary text-on-primary flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-opacity disabled:cursor-not-allowed disabled:opacity-40";
const secondaryButtonClass =
  "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors";

export default function AddRouterWizardPage() {
  const router = useRouter();
  const { token, ready } = useAccessToken();

  const [step, setStep] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Step 1
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [managementIp, setManagementIp] = useState("");
  const [macAddress, setMacAddress] = useState("");

  // Step 2
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState<string>("");

  // Created once step 1+2 are submitted together.
  const [routerId, setRouterId] = useState<string | null>(null);
  const [router_, setRouterData] = useState<RouterRead | null>(null);

  // Step 3
  const [networkCidr, setNetworkCidr] = useState("10.5.50.0/24");
  const [gatewayIp, setGatewayIp] = useState("10.5.50.1");
  const [dnsServers, setDnsServers] = useState("1.1.1.1, 8.8.8.8");
  const [networkConfig, setNetworkConfig] = useState<NetworkConfigRead | null>(null);

  // Steps 4-7 results
  const [wireguard, setWireguard] = useState<WireGuardConfigResult | null>(null);
  const [radius, setRadius] = useState<RadiusConfigResult | null>(null);
  const [hotspot, setHotspot] = useState<HotspotConfigResult | null>(null);
  const [walledGarden, setWalledGarden] = useState<WalledGardenResult | null>(null);
  const [publicToken, setPublicToken] = useState<PublicRouterTokenResult | null>(null);

  // Step 8
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);

  useEffect(() => {
    if (!ready || !token) return;
    apiFetch<ApiEnvelope<Location[]>>("/api/v1/locations?page_size=100", { accessToken: token })
      .then((res) => setLocations(res.data))
      .catch(() => setLocations([]));
  }, [ready, token]);

  function handleError(err: unknown) {
    setError(err instanceof ApiClientError ? err.message : "Something went wrong");
  }

  async function submitIdentityAndLocation() {
    if (!name.trim()) {
      setError("Router name is required");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiMutate<ApiEnvelope<RouterRead>>("/api/v1/routers", {
        accessToken: token,
        body: {
          name: name.trim(),
          location_id: locationId || null,
          model: model.trim() || null,
          management_ip: managementIp.trim() || null,
          mac_address: macAddress.trim() || null,
        },
      });
      setRouterId(res.data.id);
      setRouterData(res.data);
      setStep(3);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function submitNetworkConfig() {
    if (!routerId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiMutate<ApiEnvelope<NetworkConfigRead>>(
        `/api/v1/routers/${routerId}/provisioning/network-config`,
        {
          accessToken: token,
          method: "PUT",
          body: {
            network_cidr: networkCidr.trim(),
            gateway_ip: gatewayIp.trim(),
            dns_servers: dnsServers
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
          },
        },
      );
      setNetworkConfig(res.data);
      setStep(4);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function generateWireguard() {
    if (!routerId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiMutate<ApiEnvelope<WireGuardConfigResult>>(
        `/api/v1/routers/${routerId}/provisioning/wireguard`,
        { accessToken: token },
      );
      setWireguard(res.data);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function generateRadius() {
    if (!routerId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiMutate<ApiEnvelope<RadiusConfigResult>>(
        `/api/v1/routers/${routerId}/provisioning/radius`,
        { accessToken: token },
      );
      setRadius(res.data);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function generateHotspot() {
    if (!routerId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiMutate<ApiEnvelope<HotspotConfigResult>>(
        `/api/v1/routers/${routerId}/provisioning/hotspot`,
        { accessToken: token },
      );
      setHotspot(res.data);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function generateWalledGarden() {
    if (!routerId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiMutate<ApiEnvelope<WalledGardenResult>>(
        `/api/v1/routers/${routerId}/provisioning/walled-garden`,
        { accessToken: token },
      );
      setWalledGarden(res.data);
      const tokenRes = await apiFetch<ApiEnvelope<PublicRouterTokenResult>>(
        `/api/v1/routers/${routerId}/provisioning/public-token`,
        { accessToken: token },
      );
      setPublicToken(tokenRes.data);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function runConnectivityTest() {
    if (!routerId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiMutate<ApiEnvelope<TestConnectionResult>>(
        `/api/v1/routers/${routerId}/test-connection`,
        { accessToken: token },
      );
      setTestResult(res.data);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function completeProvisioning() {
    if (!routerId) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiMutate<ApiEnvelope<RouterRead>>(
        `/api/v1/routers/${routerId}/provisioning/complete`,
        { accessToken: token },
      );
      router.push("/dashboard/network/routers");
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Add Router"
        description="Onboard a MikroTik RouterOS 7 device: identity, network, WireGuard, RADIUS, and hotspot configuration."
      />

      <ol className="flex flex-wrap gap-2">
        {STEP_LABELS.map((label, index) => {
          const stepNumber = index + 1;
          const isDone = stepNumber < step;
          const isCurrent = stepNumber === step;
          return (
            <li
              key={label}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
                isCurrent
                  ? "bg-primary text-on-primary"
                  : isDone
                    ? "bg-secondary-container text-on-secondary-container"
                    : "bg-surface-container-high text-on-surface-variant"
              }`}
            >
              {isDone ? <Check size={12} /> : stepNumber}
              {label}
            </li>
          );
        })}
      </ol>

      {error && (
        <div className="bg-error-container text-on-error-container rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <div className="bg-surface-container-lowest flex flex-col gap-4 rounded-xl p-6 shadow-sm">
        {step === 1 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-on-surface text-lg font-semibold">1. Router identity</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1">
                <span className={labelClass}>Name *</span>
                <input
                  className={inputClass}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Kariakoo Router 1"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelClass}>Model</span>
                <input
                  className={inputClass}
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="RB750Gr3"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelClass}>Management IP</span>
                <input
                  className={inputClass}
                  value={managementIp}
                  onChange={(e) => setManagementIp(e.target.value)}
                  placeholder="192.168.88.1"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelClass}>MAC address</span>
                <input
                  className={inputClass}
                  value={macAddress}
                  onChange={(e) => setMacAddress(e.target.value)}
                  placeholder="AA:BB:CC:DD:EE:FF"
                />
              </label>
            </div>
            <button
              type="button"
              className={`${primaryButtonClass} self-end`}
              onClick={() => setStep(2)}
              disabled={!name.trim()}
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-on-surface text-lg font-semibold">2. Hotspot site/location</h2>
            <label className="flex flex-col gap-1">
              <span className={labelClass}>Location</span>
              <select
                className={inputClass}
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
              >
                <option value="">No location yet</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                    {location.city ? ` — ${location.city}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-on-surface-variant text-xs">
              Locations are managed under Network → Hotspot Sites. This router is created once
              you continue.
            </p>
            <div className="flex justify-between">
              <button type="button" className={secondaryButtonClass} onClick={() => setStep(1)}>
                Back
              </button>
              <button
                type="button"
                className={primaryButtonClass}
                onClick={submitIdentityAndLocation}
                disabled={submitting}
              >
                {submitting && <Loader2 size={16} className="animate-spin" />}
                Create router <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-on-surface text-lg font-semibold">3. Network configuration</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1">
                <span className={labelClass}>Hotspot network (CIDR)</span>
                <input
                  className={inputClass}
                  value={networkCidr}
                  onChange={(e) => setNetworkCidr(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelClass}>Gateway IP</span>
                <input
                  className={inputClass}
                  value={gatewayIp}
                  onChange={(e) => setGatewayIp(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 sm:col-span-2">
                <span className={labelClass}>DNS servers (comma-separated)</span>
                <input
                  className={inputClass}
                  value={dnsServers}
                  onChange={(e) => setDnsServers(e.target.value)}
                />
              </label>
            </div>
            <button
              type="button"
              className={`${primaryButtonClass} self-end`}
              onClick={submitNetworkConfig}
              disabled={submitting}
            >
              {submitting && <Loader2 size={16} className="animate-spin" />}
              Next <ChevronRight size={16} />
            </button>
          </div>
        )}

        {step === 4 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-on-surface text-lg font-semibold">4. WireGuard configuration</h2>
            {!wireguard ? (
              <button
                type="button"
                className={primaryButtonClass}
                onClick={generateWireguard}
                disabled={submitting}
              >
                {submitting && <Loader2 size={16} className="animate-spin" />}
                Generate WireGuard config
              </button>
            ) : (
              <>
                <CopyBlock
                  label="Paste into RouterOS terminal"
                  code={wireguard.router_config_script}
                  filename="wireguard-router.rsc"
                  warning="This is the only time the router's private key is shown — store it securely."
                />
                <CopyBlock
                  label="Append to the Network VPS's wg0.conf"
                  code={wireguard.server_peer_block}
                  filename="wg0-peer-block.conf"
                />
                <button
                  type="button"
                  className={`${primaryButtonClass} self-end`}
                  onClick={() => setStep(5)}
                >
                  Next <ChevronRight size={16} />
                </button>
              </>
            )}
          </div>
        )}

        {step === 5 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-on-surface text-lg font-semibold">5. RADIUS configuration</h2>
            {!radius ? (
              <button
                type="button"
                className={primaryButtonClass}
                onClick={generateRadius}
                disabled={submitting}
              >
                {submitting && <Loader2 size={16} className="animate-spin" />}
                Generate RADIUS config
              </button>
            ) : (
              <>
                <CopyBlock
                  label="Paste into RouterOS terminal"
                  code={radius.router_config_script}
                  filename="radius-router.rsc"
                  warning="This is the only time the RADIUS shared secret is shown."
                />
                <CopyBlock
                  label="Add to the VPS's FreeRADIUS clients.conf"
                  code={radius.nas_client_block}
                  filename="nas-client.conf"
                />
                <button
                  type="button"
                  className={`${primaryButtonClass} self-end`}
                  onClick={() => setStep(6)}
                >
                  Next <ChevronRight size={16} />
                </button>
              </>
            )}
          </div>
        )}

        {step === 6 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-on-surface text-lg font-semibold">
              6. Hotspot / captive portal configuration
            </h2>
            {!hotspot ? (
              <button
                type="button"
                className={primaryButtonClass}
                onClick={generateHotspot}
                disabled={submitting}
              >
                {submitting && <Loader2 size={16} className="animate-spin" />}
                Generate hotspot config
              </button>
            ) : (
              <>
                <CopyBlock
                  label="Paste into RouterOS terminal"
                  code={hotspot.router_config_script}
                  filename="hotspot-router.rsc"
                />
                <button
                  type="button"
                  className={`${primaryButtonClass} self-end`}
                  onClick={() => setStep(7)}
                >
                  Next <ChevronRight size={16} />
                </button>
              </>
            )}
          </div>
        )}

        {step === 7 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-on-surface text-lg font-semibold">7. Walled garden rules</h2>
            {!walledGarden ? (
              <button
                type="button"
                className={primaryButtonClass}
                onClick={generateWalledGarden}
                disabled={submitting}
              >
                {submitting && <Loader2 size={16} className="animate-spin" />}
                Generate walled garden rules
              </button>
            ) : (
              <>
                <p className="text-on-surface-variant text-xs">
                  Only these domains are reachable before login — never a wildcard:
                </p>
                <ul className="text-on-surface flex flex-wrap gap-2 text-sm">
                  {walledGarden.domains.map((domain) => (
                    <li
                      key={domain}
                      className="bg-surface-container-high rounded-full px-3 py-1 font-mono text-xs"
                    >
                      {domain}
                    </li>
                  ))}
                </ul>
                <CopyBlock
                  label="Paste into RouterOS terminal"
                  code={walledGarden.router_config_script}
                  filename="walled-garden.rsc"
                />
                {publicToken && (
                  <CopyBlock
                    label="Hotspot login redirect (use as the walled-garden login URL)"
                    code={publicToken.example_redirect_url}
                  />
                )}
                <button
                  type="button"
                  className={`${primaryButtonClass} self-end`}
                  onClick={() => setStep(8)}
                >
                  Next <ChevronRight size={16} />
                </button>
              </>
            )}
          </div>
        )}

        {step === 8 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-on-surface text-lg font-semibold">8. Connectivity test</h2>
            <p className="text-on-surface-variant text-xs">
              Once the router has the WireGuard config applied and the tunnel is up on the
              Network VPS, test that the Network Agent can reach it.
            </p>
            <button
              type="button"
              className={primaryButtonClass}
              onClick={runConnectivityTest}
              disabled={submitting}
            >
              {submitting && <Loader2 size={16} className="animate-spin" />}
              Test connection
            </button>
            {testResult && (
              <div
                className={`rounded-lg px-4 py-3 text-sm ${
                  testResult.reachable
                    ? "bg-secondary-container text-on-secondary-container"
                    : "bg-error-container text-on-error-container"
                }`}
              >
                {testResult.reachable
                  ? `Reachable (${testResult.latency_ms ?? "?"} ms)`
                  : `Not reachable yet${testResult.detail ? `: ${testResult.detail}` : ""}`}
              </div>
            )}
            <button
              type="button"
              className={`${primaryButtonClass} self-end`}
              onClick={() => setStep(9)}
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
        )}

        {step === 9 && (
          <div className="flex flex-col gap-4">
            <h2 className="text-on-surface text-lg font-semibold">9. Save router</h2>
            <p className="text-on-surface-variant text-sm">
              {router_?.name ?? "This router"} is provisioned. Confirm to mark setup complete.
            </p>
            <button
              type="button"
              className={`${primaryButtonClass} self-end`}
              onClick={completeProvisioning}
              disabled={submitting}
            >
              {submitting && <Loader2 size={16} className="animate-spin" />}
              Finish
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
