import { Send } from "lucide-react";
import type { DocsCategory } from "./types";

export const payouts: DocsCategory = {
  slug: "payouts",
  title: "Payouts",
  navLabel: "Payouts",
  description: "Requesting, approving, and tracking business payouts from your tenant wallet.",
  icon: Send,
  audience: ["Tenant Owners", "Accountants"],
  updated: "2026-09-13",
  related: ["wallet", "collections", "account"],
  sections: [
    {
      id: "payout-overview",
      title: "Payout Overview",
      blocks: [
        {
          type: "callout",
          tone: "info",
          text: "Payout processing is managed by Infinity Radius. API credentials are not required for tenant users.",
        },
        {
          type: "p",
          text: "A payout moves your available wallet balance out to your business's approved destination. Payouts go through a controlled request-and-approval process to protect against unauthorized withdrawals.",
        },
      ],
    },
    {
      id: "approved-payout-destinations",
      title: "Approved Payout Destinations",
      blocks: [
        {
          type: "p",
          text: "Payouts are only sent to a destination that has been verified and approved for your tenant. Contact support to add or change an approved payout destination.",
        },
      ],
    },
    {
      id: "requesting-a-payout",
      title: "Requesting a Payout",
      blocks: [
        {
          type: "steps",
          items: [
            "Open Finance → Payouts.",
            "Confirm your available balance covers the amount you want to withdraw.",
            "Select an approved payout destination.",
            "Enter the payout amount.",
            "Confirm the security step required for your account (such as two-factor authentication).",
            "Submit the request.",
          ],
        },
      ],
    },
    {
      id: "payout-approval",
      title: "Payout Approval",
      blocks: [
        {
          type: "p",
          text: "Larger or sensitive payouts may require a second authorized staff member to approve the request before it's processed — a maker-checker step designed to prevent a single compromised account from moving funds out.",
        },
      ],
    },
    {
      id: "payout-statuses",
      title: "Payout Statuses",
      blocks: [
        {
          type: "list",
          items: [
            "Pending Approval — awaiting a second approval before processing.",
            "Approved — approved and queued for processing.",
            "Processing — the payout is being sent to your destination.",
            "Success — funds have been sent.",
            "Failed — the payout could not be completed; funds remain in your wallet.",
            "Rejected — an approver declined the request.",
            "Cancelled — the request was cancelled before processing.",
            "Reversed — a previously successful payout was later reversed.",
          ],
        },
      ],
    },
    {
      id: "failed-and-reversed-payouts",
      title: "Failed & Reversed Payouts",
      blocks: [
        {
          type: "p",
          text: "A failed payout does not remove funds from your wallet — the amount stays available and you can request the payout again. A reversed payout returns the amount to your wallet after the fact.",
        },
      ],
    },
    {
      id: "payout-history",
      title: "Payout History",
      blocks: [
        {
          type: "p",
          text: "Finance → Payouts keeps a full history of every payout request and its status, so you can track outgoing funds over time.",
        },
      ],
    },
  ],
};
