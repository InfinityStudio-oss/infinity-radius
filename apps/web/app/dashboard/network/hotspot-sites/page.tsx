import { Radio } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function HotspotSitesPage() {
  return (
    <ResourceListPage
      title="Hotspot Sites"
      description="Physical locations where your access points are deployed."
      resourcePath="/api/v1/tenant/resources/hotspot-sites"
      columns={[
        { key: "name", header: "Site Name" },
        { key: "location", header: "Location" },
        { key: "routers", header: "Routers" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<Radio size={28} />}
      emptyTitle="No hotspot sites configured"
      emptyDescription="Add a site to start deploying routers and packages there."
      searchPlaceholder="Search sites…"
    />
  );
}
