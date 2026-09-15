import type { Metadata } from "next";
import { LegalPage, type LegalSection } from "@/components/public/legal-page";
import { PUBLIC_CONTACT } from "@/lib/public-contact";

const TITLE = "Infinity Radius Privacy Policy";
const EFFECTIVE_DATE = "September 13, 2026";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: TITLE,
};

const SECTIONS: LegalSection[] = [
  {
    id: "introduction",
    heading: "Introduction",
    body: (
      <p>
        This Privacy Policy explains how Infinity Radius (&quot;Infinity Radius&quot;,
        &quot;we&quot;, &quot;us&quot;) collects, uses, discloses, and protects information in
        connection with our multi-tenant ISP billing, hotspot, RADIUS, and network management
        platform (the &quot;Service&quot;). It applies to internet service providers, WiFi
        operators, and network operators (&quot;tenants&quot;) who use the Service, to staff
        users of tenant accounts, and to platform administrators. It does not directly govern how
        tenants handle the personal information of their own end customers — see &quot;Business
        Customer Responsibilities&quot; below.
      </p>
    ),
  },
  {
    id: "information-we-collect",
    heading: "Information We Collect",
    body: (
      <p>
        We collect information that you provide directly to us, information generated through
        your use of the Service (such as network, billing, and session records), and limited
        technical information collected automatically. The categories below describe the types
        of information involved in operating the Service.
      </p>
    ),
  },
  {
    id: "account-information",
    heading: "Account Information",
    body: (
      <p>
        When you or your organization register for the Service, we collect information such as
        name, email address, phone number, and authentication credentials, processed through our
        identity and authentication provider.
      </p>
    ),
  },
  {
    id: "business-and-tenant-information",
    heading: "Business and Tenant Information",
    body: (
      <p>
        For tenant accounts, we collect business-identifying information submitted during
        onboarding and verification, such as business name, contact details, and operating
        information relevant to configuring your tenant workspace.
      </p>
    ),
  },
  {
    id: "network-and-router-information",
    heading: "Network and Router Information",
    body: (
      <p>
        The Service is used to configure and monitor MikroTik routers, hotspot sites, and related
        network infrastructure. We process information such as router identifiers, connection and
        health status, and configuration data that tenants submit or that their network
        infrastructure reports to the platform.
      </p>
    ),
  },
  {
    id: "customer-and-hotspot-data",
    heading: "Customer and Hotspot Data",
    body: (
      <p>
        Tenants use the Service to manage their own end customers — for example, subscriber
        records, voucher usage, and hotspot session activity. This data is entered, generated, or
        uploaded by tenants and is processed by Infinity Radius on the tenant&apos;s behalf as
        part of operating the Service.
      </p>
    ),
  },
  {
    id: "payment-and-transaction-information",
    heading: "Payment and Transaction Information",
    body: (
      <p>
        The Service records transaction-level information relating to customer collections, such
        as amounts, timestamps, references, and status, so that tenants can reconcile and report
        on their business activity. Sensitive payment credentials (such as full card or mobile
        money account details) are handled by our payment processing partners, not stored
        directly by Infinity Radius except as necessary to operate collections and payouts.
      </p>
    ),
  },
  {
    id: "collections-and-payout-information",
    heading: "Collections and Payout Information",
    body: (
      <p>
        We maintain records of tenant wallet balances, collection activity, and payout requests
        and history, in order to provide tenant finance features such as ledgers, settlement, and
        disbursements.
      </p>
    ),
  },
  {
    id: "authentication-information",
    heading: "Authentication Information",
    body: (
      <p>
        We process authentication-related information, including login credentials, session
        tokens, and — where enabled — two-factor authentication data, to secure access to tenant
        and administrator accounts.
      </p>
    ),
  },
  {
    id: "device-and-technical-information",
    heading: "Device and Technical Information",
    body: (
      <p>
        We may automatically collect limited technical information when you use the Service, such
        as IP address, browser type, device information, and usage logs, for security, debugging,
        and service-reliability purposes.
      </p>
    ),
  },
  {
    id: "how-infinity-radius-uses-information",
    heading: "How Infinity Radius Uses Information",
    body: (
      <p>
        We use collected information to provide, maintain, and improve the Service; to process
        collections and payouts; to authenticate and secure accounts; to monitor and support
        network infrastructure connected to the platform; to communicate with tenants about their
        accounts; to detect and prevent fraud, abuse, and security incidents; and to comply with
        applicable legal obligations.
      </p>
    ),
  },
  {
    id: "multi-tenant-data-isolation",
    heading: "Multi-Tenant Data Isolation",
    body: (
      <p>
        Infinity Radius is a multi-tenant platform. Each tenant&apos;s business, customer,
        network, and financial data is logically separated from other tenants through
        tenant-scoped access controls and database-level isolation policies. Tenant staff users
        can access data only within the tenant workspace(s) they are authorized for.
      </p>
    ),
  },
  {
    id: "payment-processing",
    heading: "Payment Processing",
    body: (
      <p>
        Customer collections and business payouts on the platform are processed through
        integrated payment processing partners. Infinity Radius centrally manages the collections
        and payout relationship on behalf of tenants; individual tenants do not need to establish
        their own separate payment integrations to accept customer payments through the Service.
      </p>
    ),
  },
  {
    id: "service-providers",
    heading: "Service Providers",
    body: (
      <p>
        We work with third-party service providers that support the Service, including cloud
        hosting and database infrastructure, authentication services, and payment processing
        partners. These providers process information only as necessary to provide their
        respective services to us and are subject to contractual confidentiality and security
        obligations.
      </p>
    ),
  },
  {
    id: "data-security",
    heading: "Data Security",
    body: (
      <p>
        We implement reasonable technical and organizational safeguards designed to protect
        information processed through the Service, including access controls, encryption in
        transit, row-level tenant isolation, and audit logging of sensitive administrative and
        financial actions. No method of transmission or storage is completely secure, and we
        cannot guarantee absolute security.
      </p>
    ),
  },
  {
    id: "data-retention",
    heading: "Data Retention",
    body: (
      <p>
        We retain information for as long as reasonably necessary to provide the Service, comply
        with legal, accounting, or reporting obligations, resolve disputes, and enforce our
        agreements. Retention periods vary depending on the type of information and applicable
        requirements.
      </p>
    ),
  },
  {
    id: "cookies-and-session-technologies",
    heading: "Cookies and Session Technologies",
    body: (
      <p>
        The Service uses cookies and similar session technologies that are necessary to
        authenticate users and maintain secure sessions. We do not use these technologies for
        third-party advertising.
      </p>
    ),
  },
  {
    id: "user-rights",
    heading: "User Rights",
    body: (
      <p>
        Depending on your role and applicable law, you may have rights relating to the personal
        information we hold about you, such as requesting access to, correction of, or deletion
        of certain information. Requests can be submitted using the contact details below, and
        will be handled in accordance with applicable legal requirements and the platform&apos;s
        recordkeeping obligations.
      </p>
    ),
  },
  {
    id: "business-customer-responsibilities",
    heading: "Business Customer Responsibilities",
    body: (
      <p>
        Tenant organizations act as data controllers for the personal information of their own
        hotspot and network customers that they collect, enter, or process through the Service
        (for example, subscriber names and phone numbers). Tenants are responsible for ensuring
        they have an appropriate legal basis and provide appropriate notices to their own
        customers under applicable law. Infinity Radius processes that data on the tenant&apos;s
        behalf as their service provider.
      </p>
    ),
  },
  {
    id: "international-infrastructure",
    heading: "International Infrastructure and Cloud Hosting",
    body: (
      <p>
        The Service relies on third-party cloud hosting and infrastructure providers, which may
        process and store information in data center locations outside Tanzania. Where this
        occurs, we work with providers that maintain appropriate security and confidentiality
        commitments for the infrastructure underlying the Service.
      </p>
    ),
  },
  {
    id: "changes-to-privacy-policy",
    heading: "Changes to This Privacy Policy",
    body: (
      <p>
        We may update this Privacy Policy from time to time to reflect changes to the Service or
        our practices. We will update the effective date above when changes are made, and
        material changes will be communicated through the Service or by other reasonable means.
      </p>
    ),
  },
  {
    id: "contact",
    heading: "Contact",
    body: (
      <>
        <p>For privacy-related questions, contact us at:</p>
        <p>
          <a
            href={`mailto:${PUBLIC_CONTACT.generalEmail}`}
            className="text-blue-600 hover:underline"
          >
            {PUBLIC_CONTACT.generalEmail}
          </a>{" "}
          or{" "}
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

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      intro="This policy describes how Infinity Radius handles information in connection with our ISP billing, hotspot, and network management platform."
      effectiveDate={EFFECTIVE_DATE}
      sections={SECTIONS}
    />
  );
}
