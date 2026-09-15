import { LifeBuoy } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function SupportPage() {
  return (
    <ResourceListPage
      title="Support"
      description="Customer support tickets and inquiries."
      resourcePath="/api/v1/tenant/resources/support-tickets"
      columns={[
        { key: "subject", header: "Subject" },
        { key: "customer", header: "Customer" },
        { key: "priority", header: "Priority" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<LifeBuoy size={28} />}
      emptyTitle="No support tickets"
      emptyDescription="Customer support requests will appear here."
      searchPlaceholder="Search tickets…"
    />
  );
}
