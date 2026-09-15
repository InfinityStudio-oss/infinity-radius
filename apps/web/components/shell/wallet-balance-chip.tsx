"use client";

import { Wallet } from "lucide-react";
import { MoneyDisplay } from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";

interface WalletResponse {
  success: boolean;
  data: {
    available_balance_tzs: string;
  };
}

/**
 * Real available wallet balance in the top bar. Not every tenant role can
 * read the wallet (see app/api/v1/wallet.py's FINANCE_ROLES gate) — on a
 * 403/any error this renders nothing rather than an alarming error chip
 * in a persistent piece of UI every page shares.
 */
export function WalletBalanceChip() {
  const { state, data } = useApiQuery<WalletResponse>("/api/v1/wallet");

  if (state !== "success" || !data) return null;

  return (
    <div className="border-outline-variant bg-surface-container-low hidden items-center gap-2 rounded-lg border px-3 py-1.5 sm:flex">
      <span className="bg-secondary/10 text-secondary flex h-6 w-6 shrink-0 items-center justify-center rounded-md">
        <Wallet size={14} />
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-on-surface-variant text-[0.625rem] font-bold uppercase tracking-wider">
          Balance
        </span>
        <MoneyDisplay
          amount={data.data.available_balance_tzs}
          className="text-on-surface text-sm font-bold"
        />
      </span>
    </div>
  );
}
