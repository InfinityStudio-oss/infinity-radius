import { Package } from "lucide-react";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function PackagesPage() {
  return (
    <ResourceListPage
      title="Packages"
      description="WiFi access plans customers can purchase on the captive portal."
      actions={
        <button
          type="button"
          disabled
          className="bg-primary-container text-on-primary-container cursor-not-allowed rounded-lg px-4 py-2 text-sm font-semibold opacity-60"
        >
          Create Package
        </button>
      }
      resourcePath="/api/v1/tenant/resources/packages"
      columns={[
        { key: "name", header: "Package" },
        { key: "speed", header: "Speed" },
        { key: "duration", header: "Duration" },
        { key: "price", header: "Price (TZS)", align: "right" },
      ]}
      emptyIcon={<Package size={28} />}
      emptyTitle="No packages configured"
      emptyDescription="Create a package to make it available on the captive portal."
      searchPlaceholder="Search packages…"
    />
  );
}
