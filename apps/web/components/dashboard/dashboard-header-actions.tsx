import Link from "next/link";
import { FileText, Package, Router as RouterIcon, Ticket } from "lucide-react";

const OUTLINED_CLASS =
  "border-outline-variant text-on-surface hover:bg-surface-container-high flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-sm font-semibold transition-colors";
const PRIMARY_CLASS =
  "bg-primary text-on-primary flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-semibold";

/**
 * Header actions for the dashboard landing page. Every link goes to an
 * existing, already-implemented route where the real action actually
 * lives — there is no dedicated "create" endpoint for packages/vouchers
 * separate from their list pages, so those link there rather than
 * fabricating a shortcut that doesn't exist.
 */
export function DashboardHeaderActions() {
  return (
    <>
      <Link href="/dashboard/billing/packages" className={OUTLINED_CLASS}>
        <Package size={16} /> Create Package
      </Link>
      <Link href="/dashboard/billing/vouchers" className={OUTLINED_CLASS}>
        <Ticket size={16} /> Generate Voucher
      </Link>
      <Link href="/dashboard/finance/settlement-logs" className={OUTLINED_CLASS}>
        <FileText size={16} /> View Settlements
      </Link>
      <Link href="/dashboard/network/routers/add" className={PRIMARY_CLASS}>
        <RouterIcon size={16} /> Add Router
      </Link>
    </>
  );
}
