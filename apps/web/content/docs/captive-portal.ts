import { Wifi } from "lucide-react";
import type { DocsCategory } from "./types";

export const captivePortal: DocsCategory = {
  slug: "captive-portal",
  title: "Captive Portal",
  navLabel: "Captive Portal",
  description: "The customer-facing WiFi login page: buying a package or redeeming a voucher.",
  icon: Wifi,
  audience: ["Customer Care", "Tenant Admins"],
  updated: "2026-09-13",
  related: ["packages", "vouchers", "collections"],
  sections: [
    {
      id: "overview",
      title: "Captive Portal Overview",
      blocks: [
        {
          type: "p",
          text: "When a customer connects to your WiFi, their device is redirected to the Infinity Radius captive portal, branded with your tenant name. From there they can buy a package or redeem a voucher to get online.",
        },
      ],
    },
    {
      id: "customer-login",
      title: "Customer Login",
      blocks: [
        {
          type: "p",
          text: "The portal loads with your available packages shown to the customer, alongside a voucher redemption option.",
        },
      ],
    },
    {
      id: "buying-a-package",
      title: "Buying a Package",
      blocks: [
        {
          type: "steps",
          items: [
            "Customer selects a package on the portal.",
            "Customer enters their phone number.",
            "Infinity Radius initiates a payment request to the customer's phone.",
            "The portal shows a waiting screen while the payment is processed.",
            "Once payment is confirmed, the portal shows a success screen and the customer is connected.",
          ],
        },
      ],
    },
    {
      id: "voucher-login",
      title: "Voucher Login",
      blocks: [
        {
          type: "p",
          text: "Instead of paying, a customer can enter a voucher code. The code is validated instantly and, if valid, the linked package activates right away.",
        },
      ],
    },
    {
      id: "payment-waiting-screen",
      title: "Payment Waiting Screen",
      blocks: [
        {
          type: "p",
          text: "After a payment request is sent, the portal polls for the result and shows a waiting state. This usually resolves within a short time as the customer confirms payment on their phone.",
        },
      ],
    },
    {
      id: "successful-connection",
      title: "Successful Connection",
      blocks: [
        {
          type: "p",
          text: "Once payment or voucher redemption succeeds, the customer is authenticated through RADIUS and redirected back to the page they originally tried to visit.",
        },
      ],
    },
    {
      id: "troubleshooting-captive-portal-access",
      title: "Troubleshooting Captive Portal Access",
      blocks: [
        {
          type: "list",
          items: [
            "Portal doesn't load — confirm the router is Online (see MikroTik Setup).",
            "Payment stuck on waiting — see Collections → Payment Troubleshooting.",
            "Voucher rejected — confirm the code hasn't already been used or expired.",
          ],
        },
      ],
    },
  ],
};
