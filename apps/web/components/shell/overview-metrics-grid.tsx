"use client";

import type { ReactNode } from "react";
import {
  ErrorState,
  LoadingSkeletonCard,
  MetricCard,
  type MetricAccent,
} from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";
import type { MetricValue } from "@/lib/api-types";

export interface OverviewMetricDef {
  key: string;
  label: string;
  icon?: ReactNode;
  accent?: MetricAccent;
}

export interface OverviewMetricsGridProps {
  /** e.g. "/api/v1/tenant/overview" */
  overviewPath: string;
  metrics: OverviewMetricDef[];
}

/** Fetches an overview endpoint returning Record<string, MetricValue> and renders it as a MetricCard grid. */
export function OverviewMetricsGrid({ overviewPath, metrics }: OverviewMetricsGridProps) {
  const { state, data, error, refetch } = useApiQuery<Record<string, MetricValue>>(overviewPath);

  if (state === "loading") {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {metrics.map((m) => (
          <LoadingSkeletonCard key={m.key} />
        ))}
      </div>
    );
  }

  if (state === "error" || !data) {
    return (
      <ErrorState
        title="Unable to load overview metrics"
        description={error?.message}
        onRetry={refetch}
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {metrics.map((m) => {
        const metric = data[m.key];
        return (
          <MetricCard
            key={m.key}
            label={m.label}
            icon={m.icon}
            accent={m.accent}
            status={metric?.status ?? "unavailable"}
            value={metric?.value ?? undefined}
            caption={metric?.caption ?? undefined}
          />
        );
      })}
    </div>
  );
}
