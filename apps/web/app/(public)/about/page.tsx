import type { Metadata } from "next";
import { PublicPlaceholderPage } from "@/components/public/public-placeholder";

export const metadata: Metadata = {
  title: "About",
  description: "Infinity Radius is a multi-tenant ISP billing and WiFi management platform.",
};

export default function AboutPage() {
  return (
    <PublicPlaceholderPage title="About Infinity Radius">
      <p>
        Infinity Radius is a multi-tenant ISP billing and WiFi management platform, built for
        ISPs, WISPs, hotspot operators, apartment and hotel WiFi providers, campuses,
        restaurants/cafes, property managers, and public WiFi operators.
      </p>
      <p>Our initial market is Tanzania, operating in TZS on Africa/Dar_es_Salaam time.</p>
      <p>A fuller company story is coming soon.</p>
    </PublicPlaceholderPage>
  );
}
