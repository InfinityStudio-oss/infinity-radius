import type { Metadata } from "next";
import { PublicPlaceholderPage } from "@/components/public/public-placeholder";

export const metadata: Metadata = {
  title: "System Status",
  description: "Live platform status monitoring will be available here.",
};

export default function StatusPage() {
  return (
    <PublicPlaceholderPage title="System Status">
      <p>Live platform status monitoring will be available here.</p>
    </PublicPlaceholderPage>
  );
}
