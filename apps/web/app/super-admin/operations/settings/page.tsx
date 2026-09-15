import { Settings } from "lucide-react";
import { EmptyState, PageHeader } from "@infinity-radius/ui";

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Platform-wide configuration and integration credentials."
      />
      <EmptyState
        icon={<Settings size={28} />}
        title="Settings not configured"
        description="Platform configuration options will be available here in a later phase."
      />
    </div>
  );
}
