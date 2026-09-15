import { Router } from "lucide-react";
import type { DocsCategory } from "./types";

export const mikrotik: DocsCategory = {
  slug: "mikrotik",
  title: "MikroTik & Network Setup",
  navLabel: "MikroTik Setup",
  description: "Hotspot sites, adding a MikroTik router, requirements, and connectivity testing.",
  icon: Router,
  audience: ["Network Technicians", "Tenant Admins"],
  updated: "2026-09-13",
  related: ["wireguard", "radius", "troubleshooting"],
  sections: [
    {
      id: "hotspot-sites",
      title: "Hotspot Sites",
      blocks: [
        {
          type: "p",
          text: "A hotspot site represents a physical location — a shop, apartment building, campus, or hotel — where you provide WiFi access. Create a site under Network → Hotspot Sites before adding the routers installed there.",
        },
      ],
    },
    {
      id: "adding-a-mikrotik-router",
      title: "Adding a MikroTik Router",
      blocks: [
        {
          type: "steps",
          items: [
            "Go to Network → Routers → Add Router.",
            "Select the hotspot site the router belongs to.",
            "Enter a name and identifier for the router so it's easy to recognize in reports.",
            "Save the router. Infinity Radius generates the configuration needed to connect it.",
            "Apply the generated configuration on the router (see WireGuard Setup and RADIUS Setup).",
            "Confirm the router shows an Online status once connected.",
          ],
        },
      ],
    },
    {
      id: "routeros-requirements",
      title: "RouterOS Requirements",
      blocks: [
        {
          type: "list",
          items: [
            "RouterOS 7.x or later.",
            "WireGuard support (built in on RouterOS 7).",
            "Hotspot or DHCP service enabled on the customer-facing interface.",
            "Outbound internet access from the router itself, so it can reach Infinity Radius.",
          ],
        },
      ],
    },
    {
      id: "testing-router-connectivity",
      title: "Testing Router Connectivity",
      blocks: [
        {
          type: "steps",
          items: [
            "Apply the WireGuard and RADIUS configuration generated for the router.",
            "Open Network → Routers in your dashboard and locate the router.",
            "Wait a few moments for the status to update from Offline to Online.",
            "From a test device on the hotspot network, confirm the captive portal page loads.",
          ],
        },
        {
          type: "callout",
          tone: "info",
          text: "A router that stays Offline usually means the WireGuard tunnel hasn't connected yet. See Troubleshooting → Router Offline.",
        },
      ],
    },
    {
      id: "router-health-diagnostics",
      title: "Router Health & Diagnostics",
      blocks: [
        {
          type: "p",
          text: "The Network → Diagnostics screen shows each router's connection status and recent activity, so you can confirm a site is healthy without visiting it in person.",
        },
      ],
    },
  ],
};
