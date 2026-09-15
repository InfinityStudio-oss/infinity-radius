"use client";

import { Router as RouterIcon } from "lucide-react";
import {
  DashboardListSkeleton,
  EmptyState,
  ErrorState,
  RouterHealthCard,
  type RouterStatus,
} from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface RouterHealthRow {
  id: string;
  name: string;
  status: string;
  last_seen_at: string | null;
  active_users: number | null;
  latency_ms: number | null;
  cpu_load_pct: number | null;
  uptime_seconds: number | null;
}

interface RouterHealthResponse {
  success: boolean;
  data: RouterHealthRow[];
}

function formatUptime(seconds: number | null): string | null {
  if (seconds === null) return null;
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return `${days}d ${hours}h`;
}

function formatLastSeen(iso: string | null): string | null {
  if (iso === null) return null;
  return new Date(iso).toLocaleString("en-TZ", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Africa/Dar_es_Salaam",
  });
}

/** Real per-router status from the database, plus whatever live telemetry
 * actually exists (none yet — see GET /api/v1/routers/health) rendered
 * honestly as "Unavailable" rather than invented. */
export function NetworkHealthPanel() {
  const { state, data, error, refetch } =
    useApiQuery<RouterHealthResponse>("/api/v1/routers/health");

  if (state === "loading") return <DashboardListSkeleton rows={4} />;

  if (state === "error" || !data) {
    return (
      <ErrorState
        title="Router health unavailable"
        description={error?.message}
        onRetry={refetch}
      />
    );
  }

  const routers = data.data;
  if (routers.length === 0) {
    return (
      <EmptyState
        icon={<RouterIcon size={24} />}
        title="No routers configured"
        description="Add a router to see live gateway status here."
      />
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {routers.map((router) => (
        <RouterHealthCard
          key={router.id}
          name={router.name}
          status={router.status as RouterStatus}
          stats={[
            { label: "Active Users", value: router.active_users },
            { label: "Latency", value: router.latency_ms !== null ? `${router.latency_ms}ms` : null },
            { label: "CPU Load", value: router.cpu_load_pct !== null ? `${router.cpu_load_pct}%` : null },
            { label: "Uptime", value: formatUptime(router.uptime_seconds) },
            { label: "Last Seen", value: formatLastSeen(router.last_seen_at) },
          ]}
        />
      ))}
    </div>
  );
}
