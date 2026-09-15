import { requireUser } from "@/lib/auth";

export default async function PortalLayout({ children }: { children: React.ReactNode }) {
  await requireUser();
  return <div className="bg-surface min-h-screen">{children}</div>;
}
