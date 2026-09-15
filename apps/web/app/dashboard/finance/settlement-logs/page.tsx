import { FileText } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function SettlementLogsPage() {
  return (
    <ResourceListPage
      title="Settlement Logs"
      description="Batch settlement runs between collections and your wallet."
      resourcePath="/api/v1/tenant/resources/settlement-logs"
      columns={[
        { key: "batch", header: "Batch" },
        { key: "channel", header: "Channel" },
        { key: "count", header: "Transactions" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<FileText size={28} />}
      emptyTitle="No settlement logs"
      emptyDescription="Settlement runs will be logged here as they occur."
    />
  );
}
