import { Wallet as WalletIcon } from "lucide-react";
import type { DocsCategory } from "./types";

export const wallet: DocsCategory = {
  slug: "wallet",
  title: "Wallet & Settlements",
  navLabel: "Wallet & Settlements",
  description: "Available, pending, and reserved balances, settlement logs, and the ledger.",
  icon: WalletIcon,
  audience: ["Accountants", "Tenant Admins", "Tenant Owners"],
  updated: "2026-09-13",
  related: ["collections", "payouts", "reports"],
  sections: [
    {
      id: "wallet-overview",
      title: "Wallet Overview",
      blocks: [
        {
          type: "p",
          text: "Your tenant wallet tracks the funds collected on your behalf, broken into balances that reflect where the money is in the collections and payout lifecycle. Wallet figures are calculated from the platform's transaction and ledger records — not entered manually.",
        },
      ],
    },
    {
      id: "pending-balance",
      title: "Pending Balance",
      blocks: [
        {
          type: "p",
          text: "Funds from payments that are still being processed or haven't yet cleared into your available balance.",
        },
      ],
    },
    {
      id: "available-balance",
      title: "Available Balance",
      blocks: [
        {
          type: "p",
          text: "Funds that have fully settled and can be requested as a payout.",
        },
      ],
    },
    {
      id: "reserved-balance",
      title: "Reserved Balance",
      blocks: [
        {
          type: "p",
          text: "Funds set aside — for example, against a payout that has been requested but not yet completed — and therefore not available for a new payout request.",
        },
      ],
    },
    {
      id: "settlement-logs",
      title: "Settlement Logs",
      blocks: [
        {
          type: "p",
          text: "Finance → Settlement Logs shows how collected funds moved between pending, available, and reserved balances over time.",
        },
      ],
    },
    {
      id: "ledger-overview",
      title: "Ledger Overview",
      blocks: [
        {
          type: "p",
          text: "The ledger is the full, itemized record behind every wallet balance change — every collection, settlement, payout, and reversal is recorded as a ledger entry.",
        },
      ],
    },
    {
      id: "transaction-history",
      title: "Transaction History",
      blocks: [
        {
          type: "p",
          text: "Finance → Payments lists individual customer transactions, so you can look up a specific payment by customer, amount, or date.",
        },
      ],
    },
  ],
};
