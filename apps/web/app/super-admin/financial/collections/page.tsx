import { HandCoins } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function CollectionsPage() {
  return (
    <ResourceListPage
      title="Collections"
      description="Platform-wide customer payment collections via Selcom."
      resourcePath="/api/v1/super-admin/resources/collections"
      columns={[
        { key: "reference", header: "Reference" },
        { key: "tenant", header: "Provider" },
        { key: "channel", header: "Channel" },
        {
          key: "amount",
          header: "Amount",
          align: "right",
          render: (row) => <MoneyDisplay amount={(row.amount as string) ?? null} />,
        },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<HandCoins size={28} />}
      emptyTitle="No transactions yet"
      emptyDescription="Collections across all providers will appear here."
      searchPlaceholder="Search reference…"
    />
  );
}
