import { Lock } from "lucide-react";
import type { DocsCategory } from "./types";

export const wireguard: DocsCategory = {
  slug: "wireguard",
  title: "WireGuard Setup",
  navLabel: "WireGuard Setup",
  description: "Secure private networking between your routers and Infinity Radius.",
  icon: Lock,
  audience: ["Network Technicians"],
  updated: "2026-09-13",
  related: ["mikrotik", "radius", "troubleshooting"],
  sections: [
    {
      id: "overview",
      title: "Overview",
      blocks: [
        {
          type: "p",
          text: "Infinity Radius uses secure private networking (WireGuard) between supported network infrastructure and its router management services. This keeps management traffic between your router and the platform encrypted and isolated from the public internet.",
        },
        {
          type: "callout",
          tone: "note",
          text: "Infinity Radius does not publish its internal VPN server credentials. Every router gets its own unique configuration generated for it — configurations are not shared between routers or tenants.",
        },
      ],
    },
    {
      id: "client-steps",
      title: "Setting Up the Tunnel",
      blocks: [
        {
          type: "steps",
          items: [
            "Add the router in Network → Routers (see MikroTik Setup).",
            "Generate the router's configuration from the router's detail page.",
            "Apply the generated configuration on the router's WireGuard interface.",
            "Test the tunnel — the router should be able to reach the platform's management address.",
            "Confirm the router's status changes to Online in your dashboard.",
          ],
        },
      ],
    },
    {
      id: "example-configuration",
      title: "Example Configuration",
      blocks: [
        {
          type: "p",
          text: "Your generated configuration follows this shape. Replace the placeholders below with the values shown on your router's detail page — do not reuse these placeholder values.",
        },
        {
          type: "code",
          label: "Example only — not a real key",
          code: "[Interface]\nPrivateKey = YOUR_WIREGUARD_PRIVATE_KEY\nAddress = 10.x.x.x/32\n\n[Peer]\nPublicKey = YOUR_WIREGUARD_SERVER_PUBLIC_KEY\nAllowedIPs = 10.x.x.0/24\nEndpoint = YOUR_ASSIGNED_ENDPOINT:51820\nPersistentKeepalive = 25",
        },
      ],
    },
  ],
};
