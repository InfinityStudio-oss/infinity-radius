import { Router as RouterIcon } from "lucide-react";
import { RouterStatusIndicator, type RouterStatus } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function RoutersPage() {
  return (
    <ResourceListPage
      title="Routers"
      description="Every router fleet-wide, across all tenants."
      resourcePath="/api/v1/super-admin/resources/routers"
      columns={[
        { key: "name", header: "Router" },
        { key: "tenant", header: "Provider" },
        { key: "firmware", header: "Firmware" },
        {
          key: "status",
          header: "Status",
          align: "right",
          render: (row) => (
            <RouterStatusIndicator status={(row.status as RouterStatus) ?? "unknown"} />
          ),
        },
      ]}
      emptyIcon={<RouterIcon size={28} />}
      emptyTitle="No routers found"
      emptyDescription="Routers will appear here once tenants pair them with the Network Agent."
      searchPlaceholder="Search routers…"
    />
  );
}
