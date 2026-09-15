import { ServerCog } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function NetworkAgentsPage() {
  return (
    <ResourceListPage
      title="Network Agents"
      description="WireGuard-connected agent processes bridging Railway to MikroTik routers."
      resourcePath="/api/v1/super-admin/resources/network-agents"
      columns={[
        { key: "host", header: "Host" },
        { key: "region", header: "Region" },
        { key: "routers", header: "Routers", align: "right" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<ServerCog size={28} />}
      emptyTitle="No network agents registered"
      emptyDescription="Deploy a Network Agent on the Network VPS to see it here."
    />
  );
}
