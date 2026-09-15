"use client";

import { Receipt } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function PaymentsPage() {
  return (
    <ResourceListPage
      title="Payments"
      description="Customer payment transactions via Selcom Collection."
      resourcePath="/api/v1/tenant/resources/payments"
      columns={[
        { key: "reference", header: "Reference" },
        { key: "customer", header: "Customer" },
        { key: "channel", header: "Channel" },
        {
          key: "amount",
          header: "Amount",
          align: "right",
          render: (row) => <MoneyDisplay amount={(row.amount as string) ?? null} />,
        },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<Receipt size={28} />}
      emptyTitle="No transactions yet"
      emptyDescription="Payments will appear here once Selcom Collection is configured and customers start paying."
      searchPlaceholder="Search reference, phone…"
    />
  );
}
