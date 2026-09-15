import { RadioTower } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function RadiusPage() {
  return (
    <ResourceListPage
      title="RADIUS"
      description="FreeRADIUS server clusters backing authentication and accounting."
      resourcePath="/api/v1/super-admin/resources/radius-servers"
      columns={[
        { key: "cluster", header: "Cluster" },
        { key: "region", header: "Region" },
        { key: "load", header: "Load" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<RadioTower size={28} />}
      emptyTitle="No RADIUS clusters configured"
      emptyDescription="RADIUS infrastructure will appear here once a server is provisioned."
    />
  );
}
