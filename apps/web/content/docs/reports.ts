import { LineChart } from "lucide-react";
import type { DocsCategory } from "./types";

export const reports: DocsCategory = {
  slug: "reports",
  title: "Reports",
  navLabel: "Reports",
  description: "Collections, revenue, voucher, customer, session, and router reports.",
  icon: LineChart,
  audience: ["Tenant Owners", "Accountants", "Tenant Admins"],
  updated: "2026-09-13",
  related: ["collections", "wallet", "customers"],
  sections: [
    {
      id: "collections-reports",
      title: "Collections Reports",
      blocks: [
        { type: "p", text: "Review customer payments received over a given period, broken down by status and package." },
      ],
    },
    {
      id: "revenue-reports",
      title: "Revenue Reports",
      blocks: [
        { type: "p", text: "See how revenue trends over time across your packages and hotspot sites." },
      ],
    },
    {
      id: "voucher-reports",
      title: "Voucher Reports",
      blocks: [
        { type: "p", text: "Track voucher batches generated, redeemed, and outstanding, by package." },
      ],
    },
    {
      id: "customer-reports",
      title: "Customer Reports",
      blocks: [
        { type: "p", text: "Review customer counts, active packages, and access activity." },
      ],
    },
    {
      id: "session-reports",
      title: "Session Reports",
      blocks: [
        { type: "p", text: "Review session volume and duration trends across your network." },
      ],
    },
    {
      id: "router-reports",
      title: "Router Reports",
      blocks: [
        { type: "p", text: "See router online/offline history and usage by site." },
      ],
    },
    {
      id: "exporting-reports",
      title: "Exporting Reports",
      status: "coming-soon",
      blocks: [
        {
          type: "p",
          text: "Report exporting (for example, to CSV) is planned. Not yet available in all report views — check the report screen itself for an export option.",
        },
      ],
    },
  ],
};
