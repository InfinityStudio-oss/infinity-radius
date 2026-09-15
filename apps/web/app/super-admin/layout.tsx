import { requireSuperAdmin } from "@/lib/auth";
import { SuperAdminShell } from "@/components/super-admin/super-admin-shell";

export default async function SuperAdminLayout({ children }: { children: React.ReactNode }) {
  await requireSuperAdmin();
  return <SuperAdminShell>{children}</SuperAdminShell>;
}
