import { LifeBuoy } from "lucide-react";
import type { DocsCategory } from "./types";
import { PUBLIC_CONTACT } from "@/lib/public-contact";

export const troubleshooting: DocsCategory = {
  slug: "troubleshooting",
  title: "Support & Troubleshooting",
  navLabel: "Support & Troubleshooting",
  description: "Practical fixes for common router, RADIUS, payment, and payout issues.",
  icon: LifeBuoy,
  audience: ["Network Technicians", "Customer Care", "Tenant Admins"],
  updated: "2026-09-13",
  related: ["mikrotik", "radius", "collections", "payouts"],
  sections: [
    {
      id: "router-offline",
      title: "Router Offline",
      blocks: [
        {
          type: "list",
          items: [
            "Check the router has power and a working internet connection.",
            "Check the WireGuard tunnel is applied and active.",
            "Re-check the router's configuration against what Infinity Radius generated for it.",
            "Check Network → Diagnostics for the router's last-seen status.",
          ],
        },
      ],
    },
    {
      id: "radius-authentication-failure",
      title: "RADIUS Authentication Failure",
      blocks: [
        {
          type: "list",
          items: [
            "Confirm the router itself is Online.",
            "Confirm the customer's package is active and not expired.",
            "Check the customer hasn't exceeded their device or session limit.",
          ],
        },
      ],
    },
    {
      id: "customer-cannot-connect",
      title: "Customer Cannot Connect",
      blocks: [
        {
          type: "list",
          items: [
            "Confirm the router serving that customer is Online.",
            "Confirm the customer has an active package or unredeemed voucher.",
            "Ask the customer to forget and rejoin the WiFi network to trigger the captive portal again.",
          ],
        },
      ],
    },
    {
      id: "package-not-activating",
      title: "Package Not Activating",
      blocks: [
        {
          type: "list",
          items: [
            "Check the related payment's status under Collections.",
            "A package only activates once its payment status is Success.",
            "If payment succeeded but the package still hasn't activated, contact support.",
          ],
        },
      ],
    },
    {
      id: "voucher-not-working",
      title: "Voucher Not Working",
      blocks: [
        {
          type: "list",
          items: [
            "Confirm the voucher hasn't already been used — each code redeems once.",
            "Confirm the voucher hasn't expired.",
            "Double-check the code was entered exactly as printed.",
          ],
        },
      ],
    },
    {
      id: "payment-pending",
      title: "Payment Pending",
      blocks: [
        {
          type: "list",
          items: [
            "Wait briefly, then refresh the transaction status.",
            "Avoid initiating repeated payment requests unnecessarily while one is still pending.",
            "Contact support if the status remains Pending for an extended period.",
          ],
        },
      ],
    },
    {
      id: "payout-pending",
      title: "Payout Pending",
      blocks: [
        {
          type: "list",
          items: [
            "Check whether the payout is awaiting a second approval.",
            "A payout in Processing is being reconciled — this can take some time.",
            "Contact support if a payout stays Pending or Processing longer than expected.",
          ],
        },
      ],
    },
    {
      id: "contacting-support",
      title: "Contacting Support",
      blocks: [
        {
          type: "p",
          text: `For issues not covered here, reach Infinity Radius support at ${PUBLIC_CONTACT.supportEmail} or ${PUBLIC_CONTACT.phoneDisplay}.`,
        },
      ],
    },
  ],
};
