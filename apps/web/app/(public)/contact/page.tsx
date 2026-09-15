import type { Metadata } from "next";
import { Headset, Mail, Phone } from "lucide-react";
import { ContactForm } from "@/components/public/contact-form";
import { PUBLIC_CONTACT } from "@/lib/public-contact";

export const metadata: Metadata = {
  title: "Contact",
  description: "Get in touch with the Infinity Radius team.",
};

const CONNECT_ROWS = [
  {
    icon: Mail,
    label: "Business Email",
    value: PUBLIC_CONTACT.generalEmail,
    href: `mailto:${PUBLIC_CONTACT.generalEmail}`,
  },
  {
    icon: Headset,
    label: "Support",
    value: PUBLIC_CONTACT.supportEmail,
    href: `mailto:${PUBLIC_CONTACT.supportEmail}`,
  },
  {
    icon: Phone,
    label: "Phone / WhatsApp",
    value: PUBLIC_CONTACT.phoneDisplay,
    href: PUBLIC_CONTACT.phoneHref,
  },
] as const;

export default function ContactPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-16 sm:px-6 lg:px-8">
      <p className="text-xs font-semibold uppercase tracking-widest text-blue-600">Contact</p>
      <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
        Get in touch
      </h1>
      <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-600">
        Tell us about your ISP or hotspot business and what you&apos;re looking for.
      </p>

      <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
          <p className="text-lg font-bold text-slate-900">Send Us a Message</p>
          <p className="mt-1 text-sm text-slate-600">
            We&apos;ll get back to you as soon as we can.
          </p>

          <div className="mt-6">
            <ContactForm />
          </div>
        </div>

        <div className="rounded-2xl bg-blue-50 p-6 sm:p-8">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            Connect With Us
          </p>

          <div className="mt-5 space-y-4">
            {CONNECT_ROWS.map(({ icon: Icon, label, value, href }) => (
              <a
                key={label}
                href={href}
                className="flex items-start gap-3 rounded-lg transition-opacity hover:opacity-80"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-blue-600">
                  <Icon size={16} />
                </span>
                <span className="flex flex-col pt-1 leading-tight">
                  <span className="text-xs font-medium text-slate-500">{label}</span>
                  <span className="text-sm font-semibold text-slate-900">{value}</span>
                </span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
