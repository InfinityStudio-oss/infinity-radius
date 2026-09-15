import { requireActiveTenantUser } from "@/lib/auth";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  await requireActiveTenantUser();
  return <DashboardShell>{children}</DashboardShell>;
}
