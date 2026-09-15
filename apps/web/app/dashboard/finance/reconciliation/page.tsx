import { Scale } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function ReconciliationPage() {
  return (
    <ResourceListPage
      title="Reconciliation"
      description="Cross-checks between Selcom settlement reports and your ledger."
      resourcePath="/api/v1/tenant/resources/reconciliation"
      columns={[
        { key: "period", header: "Period" },
        { key: "expected", header: "Expected" },
        { key: "actual", header: "Actual" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<Scale size={28} />}
      emptyTitle="No reconciliation runs"
      emptyDescription="Reconciliation results will appear here once settlement reports are available."
    />
  );
}
