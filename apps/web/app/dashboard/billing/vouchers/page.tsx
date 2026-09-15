import { Ticket } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function VouchersPage() {
  return (
    <ResourceListPage
      title="Vouchers"
      description="Prepaid scratch-card style access codes."
      actions={
        <button
          type="button"
          disabled
          className="bg-tertiary-container text-on-surface cursor-not-allowed rounded-lg px-4 py-2 text-sm font-semibold opacity-60"
        >
          Generate Vouchers
        </button>
      }
      resourcePath="/api/v1/tenant/resources/vouchers"
      columns={[
        { key: "code", header: "Code" },
        { key: "package", header: "Package" },
        { key: "status", header: "Status" },
        { key: "created", header: "Created", align: "right" },
      ]}
      emptyIcon={<Ticket size={28} />}
      emptyTitle="No vouchers generated"
      emptyDescription="Generate a batch of vouchers to sell offline or via agents."
      searchPlaceholder="Search voucher code…"
    />
  );
}
