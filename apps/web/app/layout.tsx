import type { Metadata } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import { cn } from "@infinity-radius/ui";
import "./globals.css";

// Loads the fonts packages/config/design-tokens.css's --font-sans/--font-mono
// tokens already declared by name — self-hosted by Next.js, no external
// request at runtime. The `variable` name matches the token exactly, so
// this overrides it at the html element without touching the shared
// design-tokens.css file itself.
const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});
const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Infinity Radius",
    template: "%s | Infinity Radius",
  },
  description: "Multi-Tenant ISP Billing & WiFi Management Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en-TZ"
      className={cn("dark", plusJakartaSans.variable, jetBrainsMono.variable)}
    >
      <body className="bg-surface text-on-surface min-h-screen font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
