"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { apiMutate, ApiClientError } from "@/lib/api-client";

const BUSINESS_TYPES = [
  "ISP",
  "WISP",
  "Hotspot Operator",
  "Apartment WiFi",
  "Hotel WiFi",
  "Campus WiFi",
  "Restaurant / Cafe WiFi",
  "Property Manager",
  "Public WiFi Operator",
  "Other",
] as const;

const LABEL_CLASS = "text-xs font-semibold uppercase tracking-wide text-slate-500";
const FIELD_CLASS =
  "mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600";
const PHONE_PATTERN = /^(0[67]\d{8}|\+?255[67]\d{8})$/;

interface FormState {
  firstName: string;
  lastName: string;
  workEmail: string;
  phone: string;
  password: string;
  confirmPassword: string;
  tradingName: string;
  legalName: string;
  businessType: string;
  businessEmail: string;
  businessPhone: string;
  tin: string;
  businessAddress: string;
  acceptTerms: boolean;
  acceptPrivacy: boolean;
}

const INITIAL_STATE: FormState = {
  firstName: "",
  lastName: "",
  workEmail: "",
  phone: "",
  password: "",
  confirmPassword: "",
  tradingName: "",
  legalName: "",
  businessType: "",
  businessEmail: "",
  businessPhone: "",
  tin: "",
  businessAddress: "",
  acceptTerms: false,
  acceptPrivacy: false,
};

function validate(form: FormState): string | null {
  if (!form.firstName.trim() || !form.lastName.trim()) return "Enter your first and last name.";
  if (!/^\S+@\S+\.\S+$/.test(form.workEmail)) return "Enter a valid work email address.";
  if (!PHONE_PATTERN.test(form.phone.replace(/[\s-]/g, ""))) {
    return "Enter a valid Tanzania phone number (e.g. 07XXXXXXXX).";
  }
  if (form.password.length < 8 || !/[a-zA-Z]/.test(form.password) || !/\d/.test(form.password)) {
    return "Password must be at least 8 characters and include a letter and a number.";
  }
  if (form.password !== form.confirmPassword) return "Passwords do not match.";
  if (!form.tradingName.trim()) return "Enter your business or trading name.";
  if (!form.businessType) return "Select a business type.";
  if (!/^\S+@\S+\.\S+$/.test(form.businessEmail)) return "Enter a valid business email address.";
  if (!PHONE_PATTERN.test(form.businessPhone.replace(/[\s-]/g, ""))) {
    return "Enter a valid Tanzania business phone number.";
  }
  if (!form.businessAddress.trim()) return "Enter your business address.";
  if (!form.acceptTerms) return "You must accept the Terms of Service.";
  if (!form.acceptPrivacy) return "You must accept the Privacy Policy.";
  return null;
}

export default function GetStartedPage() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(INITIAL_STATE);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function field<K extends keyof FormState>(key: K) {
    return {
      value: form[key] as string,
      onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
        setForm((prev) => ({ ...prev, [key]: event.target.value })),
    };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validate(form);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await apiMutate("/api/v1/onboarding/register", {
        body: {
          first_name: form.firstName,
          last_name: form.lastName,
          work_email: form.workEmail,
          phone: form.phone,
          password: form.password,
          confirm_password: form.confirmPassword,
          trading_name: form.tradingName,
          legal_name: form.legalName || null,
          business_type: form.businessType,
          business_email: form.businessEmail,
          business_phone: form.businessPhone,
          tin: form.tin || null,
          business_license_number: null,
          region: null,
          district: null,
          ward: null,
          street_area: null,
          business_address: form.businessAddress,
          authorized_contact_name: null,
          authorized_contact_position: null,
          authorized_contact_phone: null,
          authorized_contact_email: null,
          accept_terms: form.acceptTerms,
          accept_privacy: form.acceptPrivacy,
        },
      });
      router.push(`/account/verify-email?email=${encodeURIComponent(form.workEmail)}`);
    } catch (submitError) {
      setError(
        submitError instanceof ApiClientError
          ? submitError.message
          : "Something went wrong — please try again.",
      );
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
      <p className="text-xs font-semibold uppercase tracking-widest text-blue-600">Get Started</p>
      <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
        Create your Infinity Radius account
      </h1>
      <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-600">
        Tell us about you and your business. We&apos;ll verify your email and review your
        business before activating your tenant dashboard.
      </p>

      <form onSubmit={handleSubmit} className="mt-10 space-y-10">
        <fieldset className="rounded-xl border border-slate-200 bg-white p-6">
          <legend className="px-1 text-sm font-bold text-slate-900">Account Owner</legend>
          <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2">
            <div>
              <label className={LABEL_CLASS}>First Name *</label>
              <input required className={FIELD_CLASS} {...field("firstName")} />
            </div>
            <div>
              <label className={LABEL_CLASS}>Last Name *</label>
              <input required className={FIELD_CLASS} {...field("lastName")} />
            </div>
            <div>
              <label className={LABEL_CLASS}>Work Email *</label>
              <input required type="email" className={FIELD_CLASS} {...field("workEmail")} />
            </div>
            <div>
              <label className={LABEL_CLASS}>Phone Number *</label>
              <input
                required
                placeholder="07XXXXXXXX"
                className={FIELD_CLASS}
                {...field("phone")}
              />
            </div>
            <div>
              <label className={LABEL_CLASS}>Password *</label>
              <input
                required
                type="password"
                autoComplete="new-password"
                className={FIELD_CLASS}
                {...field("password")}
              />
            </div>
            <div>
              <label className={LABEL_CLASS}>Confirm Password *</label>
              <input
                required
                type="password"
                autoComplete="new-password"
                className={FIELD_CLASS}
                {...field("confirmPassword")}
              />
            </div>
          </div>
        </fieldset>

        <fieldset className="rounded-xl border border-slate-200 bg-white p-6">
          <legend className="px-1 text-sm font-bold text-slate-900">Business Details</legend>
          <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2">
            <div>
              <label className={LABEL_CLASS}>Business / Trading Name *</label>
              <input required className={FIELD_CLASS} {...field("tradingName")} />
            </div>
            <div>
              <label className={LABEL_CLASS}>Legal Business Name</label>
              <input className={FIELD_CLASS} {...field("legalName")} />
            </div>
            <div>
              <label className={LABEL_CLASS}>Business Type *</label>
              <select required className={FIELD_CLASS} {...field("businessType")}>
                <option value="">Select a business type</option>
                {BUSINESS_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS}>Business Email *</label>
              <input
                required
                type="email"
                className={FIELD_CLASS}
                {...field("businessEmail")}
              />
            </div>
            <div>
              <label className={LABEL_CLASS}>Business Phone *</label>
              <input
                required
                placeholder="07XXXXXXXX"
                className={FIELD_CLASS}
                {...field("businessPhone")}
              />
            </div>
            <div>
              <label className={LABEL_CLASS}>TIN</label>
              <input className={FIELD_CLASS} {...field("tin")} />
            </div>
            <div className="sm:col-span-2">
              <label className={LABEL_CLASS}>Business Address *</label>
              <input
                required
                placeholder="Street/Ward - District - City/Region"
                className={FIELD_CLASS}
                {...field("businessAddress")}
              />
            </div>
          </div>
        </fieldset>

        <fieldset className="rounded-xl border border-slate-200 bg-white p-6">
          <legend className="px-1 text-sm font-bold text-slate-900">Consent</legend>
          <div className="mt-3 space-y-3">
            <label className="flex items-start gap-2.5 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.acceptTerms}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, acceptTerms: event.target.checked }))
                }
                className="mt-0.5 h-4 w-4 rounded border-slate-300"
              />
              <span>
                I accept the{" "}
                <Link href="/terms" target="_blank" className="text-blue-600 hover:underline">
                  Terms of Service
                </Link>{" "}
                *
              </span>
            </label>
            <label className="flex items-start gap-2.5 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.acceptPrivacy}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, acceptPrivacy: event.target.checked }))
                }
                className="mt-0.5 h-4 w-4 rounded border-slate-300"
              />
              <span>
                I accept the{" "}
                <Link href="/privacy" target="_blank" className="text-blue-600 hover:underline">
                  Privacy Policy
                </Link>{" "}
                *
              </span>
            </label>
          </div>
        </fieldset>

        {error && (
          <p role="alert" className="text-sm font-medium text-red-600">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="bg-slate-900 text-white inline-flex w-full items-center justify-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold shadow-sm transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
        >
          {submitting ? "Creating account…" : "Create Account"} <ArrowRight size={16} />
        </button>

        <p className="text-sm text-slate-600">
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-blue-600 hover:underline">
            Sign in
          </Link>
          .
        </p>
      </form>
    </div>
  );
}
