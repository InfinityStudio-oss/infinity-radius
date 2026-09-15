"use client";

import { Banknote } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function PayoutsPage() {
  return (
    <ResourceListPage
      title="Payouts"
      description="Disbursements from your wallet to your bank or mobile money account."
      resourcePath="/api/v1/tenant/resources/payouts"
      columns={[
        { key: "reference", header: "Reference" },
        { key: "channel", header: "Channel" },
        {
          key: "amount",
          header: "Amount",
          align: "right",
          render: (row) => <MoneyDisplay amount={(row.amount as string) ?? null} />,
        },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<Banknote size={28} />}
      emptyTitle="No payouts yet"
      emptyDescription="Payout history will appear here once Selcom Disbursement is configured."
    />
  );
}
