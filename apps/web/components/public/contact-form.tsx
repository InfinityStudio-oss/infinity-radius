import { Send } from "lucide-react";

const LABEL_CLASS = "text-xs font-semibold uppercase tracking-wide text-slate-500";
const FIELD_CLASS =
  "mt-1.5 w-full border-b border-slate-300 bg-transparent pb-2 text-sm text-slate-900 placeholder:text-slate-400 focus-visible:outline-none focus-visible:border-blue-600";

/**
 * UI boundary only — no email/backend integration exists yet (deferred to a
 * future task, e.g. Resend). The button stays disabled so this never
 * pretends to have sent a message.
 */
export function ContactForm() {
  return (
    <form className="space-y-6">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <label htmlFor="contact-name" className={LABEL_CLASS}>
            Full Name
          </label>
          <input
            id="contact-name"
            name="name"
            type="text"
            autoComplete="name"
            placeholder="e.g. Amani Mushi"
            className={FIELD_CLASS}
          />
        </div>

        <div>
          <label htmlFor="contact-business" className={LABEL_CLASS}>
            Business / ISP Name
          </label>
          <input
            id="contact-business"
            name="business"
            type="text"
            autoComplete="organization"
            placeholder="e.g. Amani Networks Ltd"
            className={FIELD_CLASS}
          />
        </div>

        <div>
          <label htmlFor="contact-email" className={LABEL_CLASS}>
            Email
          </label>
          <input
            id="contact-email"
            name="email"
            type="email"
            autoComplete="email"
            placeholder="you@business.co.tz"
            className={FIELD_CLASS}
          />
        </div>

        <div>
          <label htmlFor="contact-phone" className={LABEL_CLASS}>
            Phone (Optional)
          </label>
          <input
            id="contact-phone"
            name="phone"
            type="tel"
            autoComplete="tel"
            placeholder="+255 7XX XXX XXX"
            className={FIELD_CLASS}
          />
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="contact-type" className={LABEL_CLASS}>
            Business Type
          </label>
          <input
            id="contact-type"
            name="businessType"
            type="text"
            placeholder="e.g. ISP, WISP, Hotspot Operator"
            className={FIELD_CLASS}
          />
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="contact-message" className={LABEL_CLASS}>
            Message
          </label>
          <textarea
            id="contact-message"
            name="message"
            rows={4}
            placeholder="Tell us about your ISP or hotspot business"
            className={FIELD_CLASS}
          />
        </div>
      </div>

      <div>
        <button
          type="button"
          disabled
          aria-disabled="true"
          className="inline-flex w-full cursor-not-allowed items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-500 opacity-60 sm:w-auto"
        >
          Send Message <Send size={15} />
        </button>
        <p className="mt-2 text-xs text-slate-500">
          Not connected yet — this form doesn&apos;t send anything.
        </p>
      </div>
    </form>
  );
}
