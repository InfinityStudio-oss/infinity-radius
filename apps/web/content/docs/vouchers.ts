import { Ticket } from "lucide-react";
import type { DocsCategory } from "./types";

export const vouchers: DocsCategory = {
  slug: "vouchers",
  title: "Vouchers",
  navLabel: "Vouchers",
  description: "Voucher batches, redemption, and offline sales.",
  icon: Ticket,
  audience: ["Cashiers", "Tenant Admins", "Customer Care"],
  updated: "2026-09-13",
  related: ["packages", "captive-portal", "customers"],
  sections: [
    {
      id: "voucher-batches",
      title: "Voucher Batch",
      blocks: [
        {
          type: "p",
          text: "A voucher batch is a set of prepaid access codes generated together for a single package. Batches make it easy to print or hand out vouchers for offline sales.",
        },
      ],
    },
    {
      id: "quantity-and-package",
      title: "Quantity & Package",
      blocks: [
        {
          type: "p",
          text: "When generating a batch, choose the package the vouchers redeem and how many codes to generate. Each code in the batch redeems the same package.",
        },
      ],
    },
    {
      id: "generate-export-print",
      title: "Generate, Export & Print",
      blocks: [
        {
          type: "steps",
          items: [
            "Go to Billing → Vouchers → New Batch.",
            "Select the package and quantity, then generate the batch.",
            "Export the batch to distribute codes to staff or print physical vouchers.",
          ],
        },
      ],
    },
    {
      id: "redeem",
      title: "Redeem",
      blocks: [
        {
          type: "p",
          text: "A customer redeems a voucher on the captive portal by entering its code. Once redeemed, the voucher activates the linked package for that customer's device.",
        },
      ],
    },
    {
      id: "voucher-statuses",
      title: "Voucher Statuses",
      blocks: [
        {
          type: "list",
          items: [
            "Used — the voucher has been redeemed and its package activated.",
            "Disabled — the voucher has been manually deactivated and can't be redeemed.",
            "Expired — the voucher's validity window has passed without being redeemed.",
          ],
        },
        {
          type: "callout",
          tone: "info",
          text: "Each voucher code can only be redeemed once.",
        },
      ],
    },
    {
      id: "offline-voucher-sales",
      title: "Offline Voucher Sales",
      blocks: [
        {
          type: "p",
          text: "Vouchers let you sell internet access without a customer needing to pay through the captive portal directly — useful for shops and agents selling printed or shared codes.",
        },
      ],
    },
  ],
};
