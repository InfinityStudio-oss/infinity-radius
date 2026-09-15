"use client";

import Link from "next/link";
import { Plus, Router as RouterIcon } from "lucide-react";
import { RouterStatusIndicator, type RouterStatus } from "@infinity-radius/ui";
import { ResourceListPage } from "@/components/shell/resource-list-page";

export default function RoutersPage() {
  return (
    <ResourceListPage
      title="Routers"
      description="MikroTik RouterOS devices provisioned across your sites."
      resourcePath="/api/v1/tenant/resources/routers"
      actions={
        <Link
          href="/dashboard/network/routers/add"
          className="bg-primary text-on-primary flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold"
        >
          <Plus size={16} /> Add Router
        </Link>
      }
      columns={[
        { key: "name", header: "Router" },
        { key: "site", header: "Site" },
        { key: "ip", header: "Tunnel IP" },
        {
          key: "status",
          header: "Status",
          align: "right",
          render: (row) => (
            <RouterStatusIndicator status={(row.status as RouterStatus) ?? "unknown"} />
          ),
        },
      ]}
      emptyIcon={<RouterIcon size={28} />}
      emptyTitle="No routers configured"
      emptyDescription="Add a MikroTik router and pair it with the Network Agent to see it here."
      searchPlaceholder="Search routers…"
    />
  );
}
