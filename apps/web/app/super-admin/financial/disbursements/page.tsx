import { Send } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function DisbursementsPage() {
  return (
    <ResourceListPage
      title="Disbursements"
      description="Payouts released from the platform to provider wallets."
      actions={
        <button
          type="button"
          disabled
          className="bg-primary-container text-on-primary-container cursor-not-allowed rounded-lg px-4 py-2 text-sm font-semibold opacity-60"
        >
          Process Disbursement Batch
        </button>
      }
      resourcePath="/api/v1/super-admin/resources/disbursements"
      columns={[
        { key: "reference", header: "Reference" },
        { key: "tenant", header: "Provider" },
        {
          key: "amount",
          header: "Amount",
          align: "right",
          render: (row) => <MoneyDisplay amount={(row.amount as string) ?? null} />,
        },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<Send size={28} />}
      emptyTitle="No disbursements yet"
      emptyDescription="Disbursement runs will appear here once Selcom Disbursement is configured."
    />
  );
}
