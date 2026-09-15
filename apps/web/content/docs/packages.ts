import { Package } from "lucide-react";
import type { DocsCategory } from "./types";

export const packages: DocsCategory = {
  slug: "packages",
  title: "Packages",
  navLabel: "Packages",
  description: "Creating internet packages, duration, speed limits, and device limits.",
  icon: Package,
  audience: ["Tenant Admins", "Accountants"],
  updated: "2026-09-13",
  related: ["vouchers", "customers", "collections"],
  sections: [
    {
      id: "creating-internet-packages",
      title: "Creating Internet Packages",
      blocks: [
        {
          type: "steps",
          items: [
            "Go to Billing → Packages → New Package.",
            "Give the package a clear name customers will recognize (for example, \"Daily Package\").",
            "Set the price in TZS.",
            "Set the duration, speed limits, and any data or device limits.",
            "Save and activate the package so it becomes available for purchase.",
          ],
        },
        {
          type: "callout",
          tone: "note",
          text: "Example: \"Daily Package\" — a package name shown for illustration only, not a real operational price or plan.",
        },
      ],
    },
    {
      id: "package-duration",
      title: "Package Duration",
      blocks: [
        {
          type: "p",
          text: "Duration defines how long a package stays active after it's activated — for example, a fixed number of hours or days. Once the duration elapses, the customer's access ends until they buy again.",
        },
      ],
    },
    {
      id: "speed-limits",
      title: "Speed Limits",
      blocks: [
        {
          type: "p",
          text: "Each package can define separate download and upload speed limits. RADIUS applies these limits automatically once a customer is authenticated on that package.",
        },
      ],
    },
    {
      id: "data-limits",
      title: "Data Limits",
      blocks: [
        {
          type: "p",
          text: "Packages can optionally cap total data usage. Once a customer reaches their limit, their session ends, independent of remaining duration.",
        },
      ],
    },
    {
      id: "device-limits",
      title: "Device Limits",
      blocks: [
        {
          type: "p",
          text: "Device limits set how many devices can use a single package at the same time. This is enforced as a concurrent session limit in RADIUS.",
        },
      ],
    },
  ],
};
