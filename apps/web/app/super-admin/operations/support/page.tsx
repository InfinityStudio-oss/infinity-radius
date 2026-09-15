import { LifeBuoy } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function SupportPage() {
  return (
    <ResourceListPage
      title="Support"
      description="Escalated support tickets across all providers."
      resourcePath="/api/v1/super-admin/resources/support-tickets"
      columns={[
        { key: "subject", header: "Subject" },
        { key: "tenant", header: "Provider" },
        { key: "priority", header: "Priority" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<LifeBuoy size={28} />}
      emptyTitle="No support tickets"
      emptyDescription="Escalated tickets from providers will appear here."
      searchPlaceholder="Search tickets…"
    />
  );
}
