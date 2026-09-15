"use client";

import { Wallet as WalletIcon, ArrowDownToLine, ArrowUpFromLine } from "lucide-react";
import { MetricCard, MoneyDisplay, PageHeader } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function WalletPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Wallet" description="Your settlement balance and transaction history." />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MetricCard
          label="Available Balance"
          icon={<WalletIcon size={18} />}
          accent="primary"
          status="not_configured"
        />
        <MetricCard
          label="Inbound (30d)"
          icon={<ArrowDownToLine size={18} />}
          accent="secondary"
          status="not_configured"
        />
        <MetricCard
          label="Outbound (30d)"
          icon={<ArrowUpFromLine size={18} />}
          accent="tertiary"
          status="not_configured"
        />
      </div>

      <ResourceListPage
        title="Transaction History"
        resourcePath="/api/v1/tenant/resources/wallet-transactions"
        columns={[
          { key: "reference", header: "Reference" },
          { key: "type", header: "Type" },
          {
            key: "amount",
            header: "Amount",
            align: "right",
            render: (row) => <MoneyDisplay amount={(row.amount as string) ?? null} />,
          },
          { key: "date", header: "Date", align: "right" },
        ]}
        emptyIcon={<WalletIcon size={28} />}
        emptyTitle="No wallet transactions"
        emptyDescription="Inbound settlements and outbound payouts will appear here."
      />
    </div>
  );
}
