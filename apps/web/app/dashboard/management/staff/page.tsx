import { UserCircle } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function StaffPage() {
  return (
    <ResourceListPage
      title="Staff"
      description="Team members with access to this tenant's dashboard."
      actions={
        <button
          type="button"
          disabled
          className="bg-primary-container text-on-primary-container cursor-not-allowed rounded-lg px-4 py-2 text-sm font-semibold opacity-60"
        >
          Invite Staff
        </button>
      }
      resourcePath="/api/v1/tenant/resources/staff"
      columns={[
        { key: "name", header: "Name" },
        { key: "email", header: "Email" },
        { key: "role", header: "Role" },
        { key: "status", header: "Status", align: "right" },
      ]}
      emptyIcon={<UserCircle size={28} />}
      emptyTitle="No staff members"
      emptyDescription="Invite teammates to help operate this tenant."
      searchPlaceholder="Search staff…"
    />
  );
}
