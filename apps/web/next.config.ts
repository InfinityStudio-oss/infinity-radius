import type { NextConfig } from "next";

// Clickjacking/MIME-sniffing/referrer/permissions hardening only — a
// script/style Content-Security-Policy is deliberately not set here yet.
// Next.js's hydration payload needs either 'unsafe-inline' (weak) or a
// per-request nonce (requires wiring through proxy.ts) to avoid breaking
// the app, and that needs a real browser check before shipping — see
// docs/deployment.md.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
  },
  // Clickjacking protection — equivalent to X-Frame-Options: DENY but the
  // modern, CSP-based mechanism; this app is never legitimately framed.
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@infinity-radius/ui", "@infinity-radius/types"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
