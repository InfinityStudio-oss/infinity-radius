import { Building2 } from "lucide-react";
import type { DocsCategory } from "./types";

export const account: DocsCategory = {
  slug: "account",
  title: "Account & Organization",
  navLabel: "Account & Organization",
  description: "Business profile, staff accounts, roles, account status, and security.",
  icon: Building2,
  audience: ["Tenant Admins", "Tenant Owners"],
  updated: "2026-09-13",
  related: ["getting-started", "collections", "payouts"],
  sections: [
    {
      id: "business-profile",
      title: "Business Profile",
      blocks: [
        {
          type: "p",
          text: "Your business profile holds your tenant's name, contact details, and operating information. Keep it current — it's used for verification, support, and payout matching.",
        },
      ],
    },
    {
      id: "staff-accounts",
      title: "Staff Accounts",
      blocks: [
        {
          type: "p",
          text: "Tenant Owners and Tenant Admins can invite staff to their workspace under Management → Staff. Staff are always invited into an existing tenant — a new user cannot pick which tenant to join by themselves.",
        },
      ],
    },
    {
      id: "roles-and-permissions",
      title: "Roles & Permissions",
      blocks: [
        {
          type: "list",
          items: [
            "Tenant Owner — full access to the workspace, including finance and staff management.",
            "Tenant Admin — day-to-day administration: network, billing, customers, and reports.",
            "Accountant — collections, wallet, and payout screens.",
            "Network Technician — routers, hotspot sites, RADIUS, and diagnostics.",
            "Customer Care — customer records, sessions, and voucher support.",
            "Cashier — voucher sales and offline redemption.",
          ],
        },
        {
          type: "p",
          text: "Assign the narrowest role that lets a staff member do their job.",
        },
      ],
    },
    {
      id: "account-status",
      title: "Account Status",
      blocks: [
        {
          type: "list",
          items: [
            "Active — the tenant workspace is fully operational.",
            "Pending Verification — business details submitted, awaiting review.",
            "Suspended — access restricted; contact support to resolve.",
          ],
        },
      ],
    },
    {
      id: "security-best-practices",
      title: "Security Best Practices",
      blocks: [
        {
          type: "list",
          items: [
            "Use a unique, strong password for your Infinity Radius account.",
            "Enable two-factor authentication for sensitive actions where available, especially for payout approvals.",
            "Remove staff access promptly when someone leaves your organization.",
            "Never share your login credentials between staff members.",
          ],
        },
      ],
    },
  ],
};
