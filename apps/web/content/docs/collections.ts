import { Banknote } from "lucide-react";
import type { DocsCategory } from "./types";

export const collections: DocsCategory = {
  slug: "collections",
  title: "Collections",
  navLabel: "Collections",
  description: "How customer payments work, statuses, and troubleshooting.",
  icon: Banknote,
  audience: ["Accountants", "Tenant Admins", "Customer Care"],
  updated: "2026-09-13",
  related: ["wallet", "payouts", "captive-portal"],
  sections: [
    {
      id: "how-customer-payments-work",
      title: "How Customer Payments Work",
      blocks: [
        {
          type: "callout",
          tone: "info",
          text: "Payment provider integration is managed by Infinity Radius. Tenant users do not need API credentials.",
        },
        {
          type: "p",
          text: "Infinity Radius handles customer payment collections centrally on behalf of every tenant. You don't need to set up or manage a separate payment integration — collections are enabled automatically once your tenant account is active.",
        },
        {
          type: "steps",
          items: [
            "Customer chooses a package on the captive portal.",
            "Customer enters their phone number.",
            "Infinity Radius initiates a payment request to the customer.",
            "Infinity Radius verifies the payment once the customer confirms it.",
            "The transaction becomes Success and the package activates.",
            "Network access is enabled for the customer's device.",
          ],
        },
      ],
    },
    {
      id: "collection-statuses",
      title: "Collection Statuses",
      blocks: [
        {
          type: "list",
          items: [
            "Pending — the payment request has been sent and is awaiting the customer's confirmation.",
            "Processing — the customer has responded and the payment is being confirmed.",
            "Success — the payment is confirmed and the package has been activated.",
            "Failed — the payment did not complete; the customer can try again.",
            "Cancelled — the payment was cancelled before completion.",
            "Reversed — a previously successful payment was later reversed.",
          ],
        },
      ],
    },
    {
      id: "successful-payments",
      title: "Successful Payments",
      blocks: [
        {
          type: "p",
          text: "A successful payment is recorded against the customer and reflected in your tenant wallet's available balance according to the platform's settlement schedule, and it appears in Collections Reports.",
        },
      ],
    },
    {
      id: "failed-payments",
      title: "Failed Payments",
      blocks: [
        {
          type: "p",
          text: "Failed payments do not activate a package and do not affect your wallet balance. Customers can simply try again from the captive portal.",
        },
      ],
    },
    {
      id: "reversed-payments",
      title: "Reversed Payments",
      blocks: [
        {
          type: "p",
          text: "In rare cases, a completed payment may be reversed after the fact. When this happens, the transaction status updates to Reversed and the wallet balance is adjusted to reflect it.",
        },
      ],
    },
    {
      id: "payment-troubleshooting",
      title: "Payment Troubleshooting",
      blocks: [
        {
          type: "list",
          items: [
            "Status stuck on Pending — wait briefly, then refresh the transaction status before trying again.",
            "Avoid initiating repeated payment requests for the same purchase while one is still pending.",
            "If a payment stays Pending for an extended period, contact support with the customer's phone number and approximate time of payment.",
          ],
        },
      ],
    },
  ],
};
