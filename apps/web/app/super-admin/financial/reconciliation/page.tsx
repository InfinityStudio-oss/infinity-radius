import { Scale } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function ReconciliationPage() {
  return (
    <ResourceListPage
      title="Reconciliation"
      description="Platform-wide reconciliation between Selcom reports and provider ledgers."
      resourcePath="/api/v1/super-admin/resources/reconciliation"
      columns={[
        { key: "period", header: "Period" },
        { key: "tenant", header: "Provider" },
        { key: "variance", header: "Variance" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<Scale size={28} />}
      emptyTitle="No reconciliation runs"
      emptyDescription="Reconciliation results will appear here once settlement data is available."
    />
  );
}
