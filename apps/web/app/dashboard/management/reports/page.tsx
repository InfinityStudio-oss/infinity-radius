import { BarChart3 } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function ReportsPage() {
  return (
    <ResourceListPage
      title="Reports"
      description="Generated operational and financial reports."
      resourcePath="/api/v1/tenant/resources/reports"
      columns={[
        { key: "name", header: "Report" },
        { key: "range", header: "Period" },
        { key: "generated", header: "Generated" },
        { key: "format", header: "Format", align: "right" },
      ]}
      emptyIcon={<BarChart3 size={28} />}
      emptyTitle="No reports generated"
      emptyDescription="Generate a report to see it listed here."
    />
  );
}
