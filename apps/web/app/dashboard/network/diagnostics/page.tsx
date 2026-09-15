import { Stethoscope } from "lucide-react";
import { EmptyState, PageHeader } from "@infinity-radius/ui";

export default function DiagnosticsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Diagnostics"
        description="Ping, reboot, and trace tools reaching routers through the Network Agent."
      />
      <EmptyState
        icon={<Stethoscope size={28} />}
        title="Diagnostics not configured"
        description="This connects to the Network Agent's router-control endpoints, which are not implemented yet."
      />
    </div>
  );
}
