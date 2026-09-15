"use client";

import { PackageX, Gauge } from "lucide-react";
import { EmptyState, ErrorState, LoadingSkeletonCard, MoneyDisplay, cn } from "@infinity-radius/ui";
import { usePublicApiQuery } from "@/lib/hooks/use-public-api-query";
import type { ResourceListResponse } from "@/lib/api-types";

/** Mirrors apps/api/app/schemas/captive_portal.py's CaptivePortalPackageRead. */
export interface CaptivePortalPackage {
  id: string;
  name: string;
  description: string | null;
  price_tzs: string;
  duration_minutes: number | null;
  download_speed_kbps: number | null;
  upload_speed_kbps: number | null;
  device_limit: number;
}

export interface PackageSelectorProps {
  /** The signed router token from the hotspot redirect (`?router=...`) —
   * never a tenant_id or raw router id. */
  routerToken: string | null;
  selectedId: string | null;
  onSelect: (pkg: CaptivePortalPackage) => void;
}

function speedLabel(pkg: CaptivePortalPackage): string | null {
  if (!pkg.download_speed_kbps) return null;
  const down = pkg.download_speed_kbps >= 1000
    ? `${(pkg.download_speed_kbps / 1000).toFixed(1)}M`
    : `${pkg.download_speed_kbps}k`;
  if (!pkg.upload_speed_kbps) return `${down} down`;
  const up = pkg.upload_speed_kbps >= 1000
    ? `${(pkg.upload_speed_kbps / 1000).toFixed(1)}M`
    : `${pkg.upload_speed_kbps}k`;
  return `${down}/${up}`;
}

function durationLabel(pkg: CaptivePortalPackage): string | null {
  if (!pkg.duration_minutes) return null;
  if (pkg.duration_minutes % 1440 === 0) {
    const days = pkg.duration_minutes / 1440;
    return `${days} day${days === 1 ? "" : "s"}`;
  }
  if (pkg.duration_minutes % 60 === 0) {
    const hours = pkg.duration_minutes / 60;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  return `${pkg.duration_minutes} min`;
}

/** Fetches real packages for this hotspot's tenant — never a hardcoded plan list or price. */
export function PackageSelector({ routerToken, selectedId, onSelect }: PackageSelectorProps) {
  const resourcePath = routerToken
    ? `/api/v1/public/captive-portal/packages?router=${encodeURIComponent(routerToken)}`
    : null;
  const { state, data, error, refetch } = usePublicApiQuery<ResourceListResponse>(resourcePath);

  if (!routerToken) {
    return (
      <EmptyState
        icon={<PackageX size={28} />}
        title="No network detected"
        description="Open this page from your hotspot's WiFi login redirect to see available plans."
      />
    );
  }

  if (state === "loading") {
    return (
      <div className="flex flex-col gap-2">
        {[1, 2, 3].map((i) => (
          <LoadingSkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (state === "error") {
    return (
      <ErrorState title="Unable to load plans" description={error?.message} onRetry={refetch} />
    );
  }

  const packages = (data?.items ?? []) as unknown as CaptivePortalPackage[];

  if (packages.length === 0) {
    return (
      <EmptyState
        icon={<PackageX size={28} />}
        title="No packages available"
        description="This hotspot has no access plans configured yet. Contact your network administrator."
      />
    );
  }

  return (
    <div role="radiogroup" aria-label="WiFi access plans" className="flex flex-col gap-2">
      {packages.map((pkg) => {
        const active = pkg.id === selectedId;
        const speed = speedLabel(pkg);
        const duration = durationLabel(pkg);
        return (
          <button
            key={pkg.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onSelect(pkg)}
            className={cn(
              "flex items-center justify-between rounded-xl p-3 text-left shadow-sm transition-all",
              active ? "bg-primary-container/20 ring-primary ring-1" : "bg-surface-container-low",
            )}
          >
            <div className="flex min-w-0 items-center gap-3">
              <span
                className={cn(
                  "flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full",
                  active ? "bg-primary-container" : "bg-surface-container-highest",
                )}
              >
                {active && <span className="bg-on-primary-container h-2.5 w-2.5 rounded-full" />}
              </span>
              <div className="flex min-w-0 flex-col">
                <span className="text-on-surface font-bold">{pkg.name}</span>
                <div className="text-on-surface-variant flex items-center gap-2 text-xs">
                  {speed && (
                    <span className="flex items-center gap-0.5">
                      <Gauge size={14} className="text-secondary" /> {speed}
                    </span>
                  )}
                  {duration && <span>{duration}</span>}
                </div>
              </div>
            </div>
            <MoneyDisplay
              amount={pkg.price_tzs}
              currency="TZS"
              className="text-primary flex-shrink-0 text-lg font-bold"
            />
          </button>
        );
      })}
    </div>
  );
}
