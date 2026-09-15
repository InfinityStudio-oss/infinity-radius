import { Radio } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function HotspotSitesPage() {
  return (
    <ResourceListPage
      title="Hotspot Sites"
      description="Every hotspot site deployed across all tenants."
      resourcePath="/api/v1/super-admin/resources/hotspot-sites"
      columns={[
        { key: "name", header: "Site" },
        { key: "tenant", header: "Provider" },
        { key: "location", header: "Location" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<Radio size={28} />}
      emptyTitle="No hotspot sites found"
      emptyDescription="Sites will appear here once providers start deploying them."
      searchPlaceholder="Search sites…"
    />
  );
}
