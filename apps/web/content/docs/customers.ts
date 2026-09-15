import { Users } from "lucide-react";
import type { DocsCategory } from "./types";

export const customers: DocsCategory = {
  slug: "customers",
  title: "Customers & Access",
  navLabel: "Customers & Access",
  description: "Customer records, devices, active sessions, and managing internet access.",
  icon: Users,
  audience: ["Customer Care", "Tenant Admins"],
  updated: "2026-09-13",
  related: ["radius", "captive-portal", "packages"],
  sections: [
    {
      id: "customers",
      title: "Customers",
      blocks: [
        {
          type: "p",
          text: "The Customers screen lists everyone who has purchased access on your network — their contact details, current package, and access status.",
        },
      ],
    },
    {
      id: "customer-devices",
      title: "Customer Devices",
      blocks: [
        {
          type: "p",
          text: "Each customer's connected devices are tracked against their package's device limit, so you can see how many devices are using an account at a glance.",
        },
      ],
    },
    {
      id: "internet-access",
      title: "Internet Access",
      blocks: [
        {
          type: "p",
          text: "A customer's access is granted through RADIUS once they have an active package or valid voucher. Access is automatically withdrawn when a package expires or a session ends.",
        },
      ],
    },
    {
      id: "active-sessions",
      title: "Active Sessions",
      blocks: [
        {
          type: "p",
          text: "Network → Sessions shows who is currently connected, which router they're on, and how long they've been active — useful for spotting unusual usage or confirming a customer is really online.",
        },
      ],
    },
    {
      id: "disconnecting-users",
      title: "Disconnecting Users",
      blocks: [
        {
          type: "p",
          text: "Staff with the right permissions can end an active session from the Sessions screen — for example, if a device limit is being abused or a customer requests it.",
        },
      ],
    },
    {
      id: "session-expiry",
      title: "Session Expiry",
      blocks: [
        {
          type: "p",
          text: "Sessions end automatically when a package's duration or data allowance is used up. The customer is disconnected and needs to buy or activate a new package to reconnect.",
        },
      ],
    },
  ],
};
