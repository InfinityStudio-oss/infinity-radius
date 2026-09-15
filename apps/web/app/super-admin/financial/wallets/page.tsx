import { Wallet } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function WalletsPage() {
  return (
    <ResourceListPage
      title="Wallets"
      description="Provider wallet balances platform-wide."
      resourcePath="/api/v1/super-admin/resources/wallets"
      columns={[
        { key: "tenant", header: "Provider" },
        {
          key: "balance",
          header: "Balance",
          align: "right",
          render: (row) => <MoneyDisplay amount={(row.balance as string) ?? null} />,
        },
        { key: "updated", header: "Last Updated", align: "right" },
      ]}
      emptyIcon={<Wallet size={28} />}
      emptyTitle="No provider wallets found"
      emptyDescription="Provider wallet balances will appear here once tenants are onboarded."
      searchPlaceholder="Search provider…"
    />
  );
}
