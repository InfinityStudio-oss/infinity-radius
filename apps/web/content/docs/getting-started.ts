import { Rocket } from "lucide-react";
import type { DocsCategory } from "./types";

export const gettingStarted: DocsCategory = {
  slug: "getting-started",
  title: "Getting Started",
  navLabel: "Getting Started",
  description: "What Infinity Radius is, how tenant accounts get set up, and how to go live.",
  icon: Rocket,
  audience: ["ISP Owners", "WISP Owners", "Hotspot Operators", "Tenant Admins"],
  updated: "2026-09-13",
  related: ["account", "mikrotik", "packages"],
  sections: [
    {
      id: "platform-overview",
      title: "Platform Overview",
      blocks: [
        {
          type: "p",
          text: "Infinity Radius is a multi-tenant platform for ISPs, WISPs, and hotspot operators. Each business runs in its own isolated tenant workspace covering network operations, customer management, billing and vouchers, collections, tenant wallets, payouts, and reporting.",
        },
        {
          type: "list",
          items: [
            "Network — hotspot sites, MikroTik routers, RADIUS access, and live sessions.",
            "Customers — subscriber records, devices, and access status.",
            "Billing — internet packages, subscriptions, and vouchers.",
            "Finance — collections, tenant wallet balances, and payouts.",
            "Reports — collections, revenue, voucher, customer, session, and router reports.",
          ],
        },
        {
          type: "p",
          text: "Infinity Radius defaults to Tanzania: currency is TZS, and dates and session windows use the Africa/Dar_es_Salaam timezone.",
        },
      ],
    },
    {
      id: "account-registration",
      title: "Account Registration",
      status: "coming-soon",
      blocks: [
        {
          type: "p",
          text: "New tenants submit their business details through the Get Started page. Self-service account creation is being finalized — submitting the form does not yet create an account automatically.",
        },
        {
          type: "callout",
          tone: "note",
          text: "To start onboarding today, contact the Infinity Radius team using the details on the Contact page.",
        },
      ],
    },
    {
      id: "business-verification",
      title: "Business Verification",
      blocks: [
        {
          type: "p",
          text: "Before a tenant workspace is activated, the Infinity Radius team reviews the submitted business details. This step confirms the business is a legitimate ISP, WISP, or hotspot operator before enabling collections and payouts for the account.",
        },
      ],
    },
    {
      id: "first-login",
      title: "First Login",
      blocks: [
        {
          type: "steps",
          items: [
            "Go to Sign In and enter the email and password provided when your account was set up.",
            "On first login, you'll land on your tenant Dashboard, which summarizes online users, today's collections, active vouchers, and router status.",
            "If you don't have credentials yet, contact your tenant owner or Infinity Radius support.",
          ],
        },
      ],
    },
    {
      id: "getting-started-checklist",
      title: "Getting Started Checklist",
      blocks: [
        {
          type: "steps",
          items: [
            "Complete your business profile under Account settings.",
            "Add your first hotspot site.",
            "Add a MikroTik router and confirm it shows Online.",
            "Create at least one internet package.",
            "Test hotspot access end-to-end from a customer device.",
            "Review your tenant wallet and payout destination before going live.",
          ],
        },
      ],
    },
  ],
};
