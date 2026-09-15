import type { Metadata } from "next";
import { LegalPage, type LegalSection } from "@/components/public/legal-page";
import { PUBLIC_CONTACT } from "@/lib/public-contact";

// INTERNAL NOTE (not rendered): this draft is written to be professional and
// legally cautious, but final production Terms of Service should be
// reviewed by qualified Tanzanian legal counsel before general availability.

const TITLE = "Infinity Radius Terms of Service";
const EFFECTIVE_DATE = "September 13, 2026";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: TITLE,
};

const SECTIONS: LegalSection[] = [
  {
    id: "acceptance-of-terms",
    heading: "Acceptance of Terms",
    body: (
      <p>
        These Terms of Service (&quot;Terms&quot;) govern access to and use of the Infinity
        Radius platform (the &quot;Service&quot;). By creating an account, registering a tenant
        organization, or otherwise using the Service, you agree to be bound by these Terms.
      </p>
    ),
  },
  {
    id: "infinity-radius-services",
    heading: "Infinity Radius Services",
    body: (
      <p>
        Infinity Radius provides a multi-tenant platform for ISP billing, hotspot and voucher
        management, MikroTik network integration, RADIUS authentication, customer management,
        collections, tenant wallets, and business payouts.
      </p>
    ),
  },
  {
    id: "eligibility",
    heading: "Eligibility",
    body: (
      <p>
        You must be authorized to act on behalf of the business or organization you register, and
        able to form a binding agreement, to use the Service.
      </p>
    ),
  },
  {
    id: "account-registration",
    heading: "Account Registration",
    body: (
      <p>
        You agree to provide accurate and current information when registering for the Service
        and to keep your account credentials confidential. You are responsible for activity that
        occurs under your account.
      </p>
    ),
  },
  {
    id: "business-verification",
    heading: "Business Verification",
    body: (
      <p>
        We may request additional business information or documentation to verify a tenant
        organization before or during onboarding. We may decline, suspend, or limit an account if
        verification cannot be reasonably completed.
      </p>
    ),
  },
  {
    id: "tenant-accounts",
    heading: "Tenant Accounts",
    body: (
      <p>
        A &quot;tenant&quot; is an ISP, WISP, hotspot operator, or similar organization operating
        its own isolated workspace on the platform. Tenants are responsible for their workspace
        configuration, staff access, and the business activity conducted through their tenant
        account.
      </p>
    ),
  },
  {
    id: "user-and-staff-accounts",
    heading: "User and Staff Accounts",
    body: (
      <p>
        Tenant organizations may create staff user accounts with role-based access to their
        workspace. Tenants are responsible for managing staff access, including promptly removing
        access for staff who no longer require it.
      </p>
    ),
  },
  {
    id: "isp-and-hotspot-responsibilities",
    heading: "ISP and Hotspot Responsibilities",
    body: (
      <p>
        Tenants are solely responsible for their own network operations, customer relationships,
        pricing, legal compliance in their jurisdiction, and the accuracy of information they
        enter into the Service, including customer, package, and voucher data.
      </p>
    ),
  },
  {
    id: "router-and-network-configuration",
    heading: "Router and Network Configuration",
    body: (
      <p>
        Tenants are responsible for the correct configuration, security, and maintenance of their
        own MikroTik routers and network infrastructure connected to the Service. Infinity Radius
        provides tools to configure and monitor connected infrastructure but does not control
        tenant-owned physical network equipment.
      </p>
    ),
  },
  {
    id: "radius-services",
    heading: "RADIUS Services",
    body: (
      <p>
        The Service provides RADIUS-based authentication and accounting functionality for tenant
        networks. Tenants are responsible for the accuracy of subscriber and package data used to
        authorize customer network access.
      </p>
    ),
  },
  {
    id: "customer-internet-access",
    heading: "Customer Internet Access",
    body: (
      <p>
        Infinity Radius is not a party to the relationship between a tenant and its own internet
        or hotspot customers. Tenants are responsible for the internet access, service levels, and
        support they provide to their own customers.
      </p>
    ),
  },
  {
    id: "packages-and-vouchers",
    heading: "Packages and Vouchers",
    body: (
      <p>
        Tenants configure their own internet packages, pricing, and vouchers through the Service.
        Infinity Radius is not responsible for a tenant&apos;s pricing decisions or package
        offerings.
      </p>
    ),
  },
  {
    id: "collections",
    heading: "Collections",
    body: (
      <p>
        The Service facilitates collection of payments from tenant customers through integrated
        payment processing partners. Collected amounts are recorded to the relevant tenant wallet
        in accordance with the platform&apos;s ledger and settlement processes.
      </p>
    ),
  },
  {
    id: "tenant-wallets",
    heading: "Tenant Wallets",
    body: (
      <p>
        Each tenant has a wallet reflecting collected funds, pending amounts, reserved amounts,
        and available balance, maintained by the Service&apos;s accounting and ledger systems.
        Wallet balances are not a bank deposit and do not accrue interest.
      </p>
    ),
  },
  {
    id: "payouts-and-disbursements",
    heading: "Payouts and Disbursements",
    body: (
      <p>
        Tenants may request payouts of available wallet balances, subject to the platform&apos;s
        payout controls, which may include maker-checker approval and verification steps designed
        to protect against unauthorized withdrawals.
      </p>
    ),
  },
  {
    id: "fees-and-commercial-terms",
    heading: "Fees and Commercial Terms",
    body: (
      <p>
        Use of the Service, including collections and payouts, may be subject to fees as
        separately communicated to tenants. We may update fees with reasonable advance notice.
      </p>
    ),
  },
  {
    id: "reversals-and-refunds",
    heading: "Reversals and Refunds",
    body: (
      <p>
        Certain transactions may be reversed, disputed, or refunded in accordance with the
        policies of our payment processing partners and applicable payment network rules. Tenants
        agree that their wallet may be adjusted to reflect such reversals.
      </p>
    ),
  },
  {
    id: "prohibited-activities",
    heading: "Prohibited Activities",
    body: (
      <p>
        You agree not to use the Service for unlawful purposes, to misrepresent transactions or
        business information, to attempt to circumvent tenant data isolation or access controls,
        or to interfere with the security or normal operation of the Service.
      </p>
    ),
  },
  {
    id: "security-obligations",
    heading: "Security Obligations",
    body: (
      <p>
        You agree to use reasonable safeguards to protect your account credentials, including
        enabling available security features such as two-factor authentication for sensitive
        actions, and to notify us promptly of any suspected unauthorized access.
      </p>
    ),
  },
  {
    id: "service-availability",
    heading: "Service Availability",
    body: (
      <p>
        We aim to provide reliable access to the Service but do not guarantee uninterrupted or
        error-free operation. The Service may be temporarily unavailable for maintenance,
        updates, or reasons outside our control.
      </p>
    ),
  },
  {
    id: "third-party-services",
    heading: "Third-Party Services",
    body: (
      <p>
        The Service integrates with third-party infrastructure and payment processing partners.
        We are not responsible for the acts, omissions, or availability of third-party services
        outside our reasonable control.
      </p>
    ),
  },
  {
    id: "suspension-and-termination",
    heading: "Suspension and Termination",
    body: (
      <p>
        We may suspend or terminate access to the Service for a tenant or user account for
        material breach of these Terms, suspected fraud or abuse, or as required by law, subject
        to reasonable notice where practicable.
      </p>
    ),
  },
  {
    id: "intellectual-property",
    heading: "Intellectual Property",
    body: (
      <p>
        Infinity Radius and its licensors retain all rights, title, and interest in and to the
        Service, excluding tenant-owned business and customer data entered into the platform.
      </p>
    ),
  },
  {
    id: "confidentiality",
    heading: "Confidentiality",
    body: (
      <p>
        Each party agrees to protect the other party&apos;s confidential information disclosed in
        connection with the Service using at least reasonable care, and to use it only as
        necessary to perform under these Terms.
      </p>
    ),
  },
  {
    id: "data-protection",
    heading: "Data Protection",
    body: (
      <p>
        Our collection and use of information in connection with the Service is described in our{" "}
        <a href="/privacy" className="text-blue-600 hover:underline">
          Privacy Policy
        </a>
        , which forms part of these Terms.
      </p>
    ),
  },
  {
    id: "limitation-of-liability",
    heading: "Limitation of Liability",
    body: (
      <p>
        To the maximum extent permitted by applicable law, Infinity Radius will not be liable for
        indirect, incidental, or consequential damages arising from use of the Service, and our
        aggregate liability for direct damages will be limited as further specified in a
        commercial agreement between the parties, where applicable.
      </p>
    ),
  },
  {
    id: "indemnification",
    heading: "Indemnification",
    body: (
      <p>
        You agree to indemnify and hold Infinity Radius harmless from claims arising out of your
        misuse of the Service, your violation of these Terms, or your violation of applicable law
        in your own business operations.
      </p>
    ),
  },
  {
    id: "changes-to-the-service",
    heading: "Changes to the Service",
    body: (
      <p>
        We may modify, add to, or discontinue features of the Service from time to time. We will
        use reasonable efforts to communicate material changes affecting tenant operations.
      </p>
    ),
  },
  {
    id: "changes-to-these-terms",
    heading: "Changes to These Terms",
    body: (
      <p>
        We may update these Terms from time to time. We will update the effective date above when
        changes are made, and continued use of the Service after changes take effect constitutes
        acceptance of the updated Terms.
      </p>
    ),
  },
  {
    id: "governing-law",
    heading: "Governing Law",
    body: (
      <p>
        These Terms are intended to be interpreted in a manner consistent with the laws
        applicable in the United Republic of Tanzania, Infinity Radius&apos;s initial market,
        without prejudice to any mandatory local law that may apply to a specific tenant.
      </p>
    ),
  },
  {
    id: "contact",
    heading: "Contact",
    body: (
      <>
        <p>Infinity Radius</p>
        <p>
          Email:{" "}
          <a
            href={`mailto:${PUBLIC_CONTACT.generalEmail}`}
            className="text-blue-600 hover:underline"
          >
            {PUBLIC_CONTACT.generalEmail}
          </a>
        </p>
        <p>
          Support:{" "}
          <a
            href={`mailto:${PUBLIC_CONTACT.supportEmail}`}
            className="text-blue-600 hover:underline"
          >
            {PUBLIC_CONTACT.supportEmail}
          </a>
        </p>
        <p>
          Phone:{" "}
          <a href={PUBLIC_CONTACT.phoneHref} className="text-blue-600 hover:underline">
            {PUBLIC_CONTACT.phoneDisplay}
          </a>
        </p>
      </>
    ),
  },
];

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      intro="These Terms of Service govern use of the Infinity Radius ISP billing, hotspot, and network management platform."
      effectiveDate={EFFECTIVE_DATE}
      sections={SECTIONS}
    />
  );
}
