import { Layers } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function TenantPlansPage() {
  return (
    <ResourceListPage
      title="Tenant Plans"
      description="Subscription tiers offered to providers on the platform."
      resourcePath="/api/v1/super-admin/resources/tenant-plans"
      columns={[
        { key: "name", header: "Plan" },
        {
          key: "price",
          header: "Price",
          align: "right",
          render: (row) => <MoneyDisplay amount={(row.price as string) ?? null} />,
        },
        { key: "tenants", header: "Tenants", align: "right" },
      ]}
      emptyIcon={<Layers size={28} />}
      emptyTitle="No plans configured"
      emptyDescription="Define subscription tiers to offer to providers."
    />
  );
}
