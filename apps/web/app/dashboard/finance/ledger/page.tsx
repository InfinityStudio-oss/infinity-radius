"use client";

import { BookOpen } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function LedgerPage() {
  return (
    <ResourceListPage
      title="Ledger"
      description="Immutable double-entry record of every financial event."
      resourcePath="/api/v1/tenant/resources/ledger"
      columns={[
        { key: "entry", header: "Entry" },
        { key: "account", header: "Account" },
        {
          key: "amount",
          header: "Amount",
          align: "right",
          render: (row) => <MoneyDisplay amount={(row.amount as string) ?? null} />,
        },
        { key: "date", header: "Date", align: "right" },
      ]}
      emptyIcon={<BookOpen size={28} />}
      emptyTitle="No ledger entries"
      emptyDescription="Every payment, payout, and adjustment will be recorded here."
    />
  );
}
