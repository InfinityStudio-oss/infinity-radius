import { UsersRound } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function RadiusUsersPage() {
  return (
    <ResourceListPage
      title="RADIUS Users"
      description="Authentication identities provisioned in FreeRADIUS."
      resourcePath="/api/v1/tenant/resources/radius-users"
      columns={[
        { key: "username", header: "Username" },
        { key: "package", header: "Package" },
        { key: "created", header: "Created" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<UsersRound size={28} />}
      emptyTitle="No RADIUS users found"
      emptyDescription="RADIUS identities will appear here once FreeRADIUS is connected."
      searchPlaceholder="Search username…"
    />
  );
}
