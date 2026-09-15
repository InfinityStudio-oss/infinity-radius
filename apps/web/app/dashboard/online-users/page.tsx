import { Wifi } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function OnlineUsersPage() {
  return (
    <ResourceListPage
      title="Online Users"
      description="Customers currently connected to your network in real time."
      resourcePath="/api/v1/tenant/resources/online-users"
      columns={[
        { key: "user", header: "User / MAC" },
        { key: "site", header: "Hotspot Site" },
        { key: "ip", header: "IP Address" },
        { key: "uptime", header: "Uptime", align: "right" },
      ]}
      emptyIcon={<Wifi size={28} />}
      emptyTitle="No online users"
      emptyDescription="Connected users will appear here once RADIUS accounting is streaming."
      searchPlaceholder="Filter MAC, IP, user…"
    />
  );
}
