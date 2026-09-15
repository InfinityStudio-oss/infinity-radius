import { Activity } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function SessionsPage() {
  return (
    <ResourceListPage
      title="Sessions"
      description="Real-time RADIUS interim-accounting stream."
      resourcePath="/api/v1/tenant/resources/sessions"
      columns={[
        { key: "user", header: "User / MAC" },
        { key: "site", header: "Hotspot Node" },
        { key: "traffic", header: "Traffic (DL / UL)" },
        { key: "uptime", header: "Uptime", align: "right" },
      ]}
      emptyIcon={<Activity size={28} />}
      emptyTitle="No active sessions"
      emptyDescription="Active subscriber sessions will stream here in real time."
      searchPlaceholder="Filter MAC, IP, user…"
    />
  );
}
