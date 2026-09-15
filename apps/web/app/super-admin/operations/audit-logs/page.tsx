import { History } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function AuditLogsPage() {
  return (
    <ResourceListPage
      title="Audit Logs"
      description="Immutable record of every administrative action on the platform."
      resourcePath="/api/v1/super-admin/resources/audit-logs"
      columns={[
        { key: "timestamp", header: "Timestamp" },
        { key: "actor", header: "Actor" },
        { key: "action", header: "Action" },
        { key: "target", header: "Target", align: "right" },
      ]}
      emptyIcon={<History size={28} />}
      emptyTitle="No audit events"
      emptyDescription="Administrative actions will be recorded here as they happen."
      searchPlaceholder="Search audit log…"
    />
  );
}
