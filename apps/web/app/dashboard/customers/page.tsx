import { Users } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function CustomersPage() {
  return (
    <ResourceListPage
      title="Customers"
      description="Every subscriber who has registered on your network."
      resourcePath="/api/v1/tenant/resources/customers"
      columns={[
        { key: "name", header: "Name" },
        { key: "phone", header: "Phone" },
        { key: "status", header: "Status" },
        { key: "joined", header: "Joined", align: "right" },
      ]}
      emptyIcon={<Users size={28} />}
      emptyTitle="No customers found"
      emptyDescription="Customers will appear here once they register or are added to your network."
      searchPlaceholder="Search by name, phone, or email…"
    />
  );
}
