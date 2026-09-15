import { Database, HeartPulse, RadioTower, ServerCog } from "lucide-react";
import { PageHeader } from "@infinity-radius/ui";
import { OverviewMetricsGrid } from "@/components/shell/overview-metrics-grid";

const SUBSYSTEMS = [
  {
    key: "radius_cluster",
    label: "RADIUS Cluster",
    icon: <RadioTower size={18} />,
    accent: "secondary" as const,
  },
  {
    key: "network_agents",
    label: "Network Agents",
    icon: <ServerCog size={18} />,
    accent: "tertiary" as const,
  },
  { key: "database", label: "Database", icon: <Database size={18} />, accent: "primary" as const },
  {
    key: "payment_gateway",
    label: "Payment Gateway",
    icon: <HeartPulse size={18} />,
    accent: "warning" as const,
  },
];

export default function SystemHealthPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="System Health" description="Live status of every platform subsystem." />
      <OverviewMetricsGrid overviewPath="/api/v1/super-admin/system-health" metrics={SUBSYSTEMS} />
    </div>
  );
}
