import { Repeat } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function SubscriptionsPage() {
  return (
    <ResourceListPage
      title="Subscriptions"
      description="Recurring customer subscriptions to your packages."
      resourcePath="/api/v1/tenant/resources/subscriptions"
      columns={[
        { key: "customer", header: "Customer" },
        { key: "package", header: "Package" },
        { key: "renews", header: "Renews" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<Repeat size={28} />}
      emptyTitle="No subscriptions found"
      emptyDescription="Recurring subscriptions will appear here once customers subscribe."
      searchPlaceholder="Search subscriptions…"
    />
  );
}
