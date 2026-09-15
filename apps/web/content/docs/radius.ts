import { Radio } from "lucide-react";
import type { DocsCategory } from "./types";

export const radius: DocsCategory = {
  slug: "radius",
  title: "RADIUS Setup",
  navLabel: "RADIUS Setup",
  description: "How RADIUS controls authentication, speed, session duration, and accounting.",
  icon: Radio,
  audience: ["Network Technicians", "Customer Care"],
  updated: "2026-09-13",
  related: ["mikrotik", "wireguard", "troubleshooting"],
  sections: [
    {
      id: "what-radius-controls",
      title: "What RADIUS Controls",
      blocks: [
        {
          type: "list",
          items: [
            "Authentication — deciding whether a customer's login is accepted.",
            "Package speed — applying the download/upload limits of the customer's active package.",
            "Session duration — how long a session may run before re-authentication.",
            "Concurrent sessions — how many devices a customer may use at once.",
            "Accounting — recording session start, stop, and usage for reports.",
          ],
        },
      ],
    },
    {
      id: "configuring-a-router",
      title: "Configuring a Router as a RADIUS Client",
      blocks: [
        {
          type: "steps",
          items: [
            "Open the router's detail page under Network → Routers.",
            "Generate the RADIUS client configuration for that router.",
            "Apply the generated shared secret and server addresses on the router's RADIUS client settings.",
            "Enable RADIUS accounting on the router's hotspot service.",
          ],
        },
        {
          type: "code",
          label: "Example only — not a real secret",
          code: "RADIUS server: YOUR_RADIUS_SERVER_ADDRESS\nAuthentication port: 1812\nAccounting port: 1813\nShared secret: YOUR_RADIUS_SECRET",
        },
        {
          type: "callout",
          tone: "note",
          text: "Each router is issued its own shared secret when it's added. Infinity Radius does not publish a shared or default secret — do not reuse a secret across routers.",
        },
      ],
    },
    {
      id: "common-statuses",
      title: "Common Authentication Statuses",
      blocks: [
        {
          type: "list",
          items: [
            "Access Accepted — the customer is authenticated and access is granted.",
            "Access Rejected — credentials or voucher code are invalid.",
            "Expired Subscription — the customer's package has run out and needs renewal.",
            "No Active Package — the customer has no active package or voucher on file.",
            "Session Limit Reached — the customer has hit their concurrent device limit.",
          ],
        },
      ],
    },
  ],
};
