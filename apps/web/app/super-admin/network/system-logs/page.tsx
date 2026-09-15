import { ScrollText } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function SystemLogsPage() {
  return (
    <ResourceListPage
      title="System Logs"
      description="Platform-level infrastructure and error logs."
      resourcePath="/api/v1/super-admin/resources/system-logs"
      columns={[
        { key: "timestamp", header: "Timestamp" },
        { key: "service", header: "Service" },
        { key: "level", header: "Level" },
        { key: "message", header: "Message" },
      ]}
      emptyIcon={<ScrollText size={28} />}
      emptyTitle="No log entries"
      emptyDescription="Infrastructure logs will stream here once services are connected."
      searchPlaceholder="Search logs…"
    />
  );
}
