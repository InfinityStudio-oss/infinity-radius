import { Banknote, Radio, Router, Ticket, Users, Wallet } from "lucide-react";
import { PublicLogo } from "./public-logo";

const STATUS_ROWS = [
  { icon: Router, label: "Network", value: "Connected" },
  { icon: Radio, label: "RADIUS", value: "Active" },
  { icon: Ticket, label: "Packages", value: "Manage" },
  { icon: Users, label: "Customers", value: "Manage" },
  { icon: Wallet, label: "Wallet", value: "Manage" },
  { icon: Banknote, label: "Payouts", value: "Manage" },
] as const;

/**
 * Marketing illustration only — a stylized device frame around a compact
 * "tenant portal" card. Deliberately shows generic status/labels, never a
 * fabricated number (no fake balances, user counts, router counts, etc).
 */
export function HeroProductVisual() {
  return (
    <div className="relative mx-auto w-full max-w-xl" aria-hidden="true">
      <div className="absolute -inset-10 -z-10 rounded-[3rem] bg-gradient-to-br from-blue-100 via-cyan-50 to-transparent blur-2xl" />

      <div className="rounded-[2rem] border border-slate-200 bg-white p-3 shadow-xl shadow-slate-900/10">
        <div className="rounded-3xl border border-slate-100 bg-slate-50 p-7">
          <div className="flex items-center justify-between">
            <PublicLogo variant="mark" className="h-11" />
            <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3.5 py-1.5 text-sm font-medium text-emerald-700">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Online
            </span>
          </div>

          <div className="mt-7 grid grid-cols-2 gap-4">
            {STATUS_ROWS.map(({ icon: Icon, label, value }) => (
              <div
                key={label}
                className="flex items-center gap-3.5 rounded-2xl border border-slate-200 bg-white px-4 py-4"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
                  <Icon size={20} />
                </span>
                <span className="flex flex-col leading-tight">
                  <span className="text-sm font-medium text-slate-400">{label}</span>
                  <span className="text-base font-semibold text-slate-800">{value}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
