# ruff: noqa: E501
"""One builder per EmailEventType — each returns (subject, html). Every
user-supplied value is HTML-escaped before interpolation; nothing here
ever includes a password or a raw internal id beyond what the recipient
already needs (a tenant_id in the admin review link, since it's the
Super Admin's own review page)."""

import html
from datetime import datetime
from uuid import UUID

from app.integrations.resend.templates.base import render_button, render_email


def _esc(value: str | None) -> str:
    return html.escape(value) if value else "&mdash;"


def verification_email(*, app_url: str, first_name: str, verify_url: str) -> tuple[str, str]:
    subject = "Verify your Infinity Radius account"
    body = f"""\
<p>Hi {_esc(first_name)},</p>
<p>Thanks for creating an Infinity Radius account. Please verify your email address to continue.</p>
{render_button(href=verify_url, label="Verify Email")}
<p style="margin-top:20px;">Verifying your email is one of two steps — your business details have
also been submitted for platform review. You'll be able to access your tenant dashboard once
both your email is verified <em>and</em> the Infinity Radius team approves your business.</p>
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)


def admin_new_tenant_email(
    *,
    app_url: str,
    tenant_id: UUID,
    business_name: str,
    legal_name: str | None,
    business_type: str | None,
    owner_name: str,
    owner_email: str,
    owner_phone: str,
    business_email: str,
    business_phone: str,
    tin: str | None,
    business_license_number: str | None,
    region: str | None,
    district: str | None,
    ward: str | None,
    submitted_at: datetime,
) -> tuple[str, str]:
    subject = "New Infinity Radius client awaiting approval"
    review_url = f"{app_url}/super-admin/tenants/{tenant_id}"
    rows = [
        ("Business Name", business_name),
        ("Legal Name", legal_name),
        ("Business Type", business_type),
        ("Owner Name", owner_name),
        ("Owner Email", owner_email),
        ("Owner Phone", owner_phone),
        ("Business Email", business_email),
        ("Business Phone", business_phone),
        ("TIN", tin),
        ("Business Licence Number", business_license_number),
        ("Region", region),
        ("District", district),
        ("Ward", ward),
        ("Submitted At", submitted_at.strftime("%Y-%m-%d %H:%M UTC")),
    ]
    table_rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748b;">{_esc(label)}</td>'
        f'<td style="padding:4px 0;color:#0f172a;font-weight:500;">{_esc(str(value) if value else None)}</td></tr>'
        for label, value in rows
    )
    body = f"""\
<p>A new tenant has submitted business details and is awaiting review.</p>
<table role="presentation" style="font-size:14px;margin-top:8px;">{table_rows}</table>
{render_button(href=review_url, label="Review Client")}
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)


def tenant_approved_email(*, app_url: str, first_name: str) -> tuple[str, str]:
    subject = "Your Infinity Radius account has been approved"
    dashboard_url = f"{app_url}/login"
    body = f"""\
<p>Hi {_esc(first_name)},</p>
<p>Your business has been approved and your Infinity Radius account is now active.</p>
<p>You can now sign in and begin setting up:</p>
<ul style="padding-left:20px;">
  <li>Hotspot Sites</li>
  <li>MikroTik Routers</li>
  <li>Packages</li>
  <li>Vouchers</li>
  <li>Customers</li>
  <li>Network Access</li>
</ul>
<p>Collections and payouts are managed centrally by Infinity Radius according to your approved
account configuration.</p>
{render_button(href=dashboard_url, label="Open Dashboard")}
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)


def tenant_rejected_email(*, app_url: str, first_name: str, reason: str) -> tuple[str, str]:
    subject = "Your Infinity Radius application was not approved"
    body = f"""\
<p>Hi {_esc(first_name)},</p>
<p>After review, we're unable to approve your Infinity Radius business application at this time.</p>
<p><strong>Reason:</strong> {_esc(reason)}</p>
<p>If you believe this is a mistake or would like to discuss it, please contact support.</p>
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)


def more_information_required_email(
    *, app_url: str, first_name: str, message: str
) -> tuple[str, str]:
    subject = "Additional information needed for your Infinity Radius application"
    action_url = f"{app_url}/account/action-required"
    body = f"""\
<p>Hi {_esc(first_name)},</p>
<p>We need a bit more information before we can approve your business application.</p>
<p><strong>Message from the Infinity Radius team:</strong></p>
<p style="background-color:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;">{_esc(message)}</p>
{render_button(href=action_url, label="Update Your Application")}
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)


def tenant_suspended_email(*, app_url: str, first_name: str, reason: str | None) -> tuple[str, str]:
    subject = "Your Infinity Radius account has been suspended"
    body = f"""\
<p>Hi {_esc(first_name)},</p>
<p>Your Infinity Radius account has been suspended and dashboard access is currently restricted.</p>
{f'<p><strong>Reason:</strong> {_esc(reason)}</p>' if reason else ""}
<p>Please contact support if you have questions about this.</p>
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)


def tenant_reactivated_email(*, app_url: str, first_name: str) -> tuple[str, str]:
    subject = "Your Infinity Radius account has been reactivated"
    dashboard_url = f"{app_url}/login"
    body = f"""\
<p>Hi {_esc(first_name)},</p>
<p>Your Infinity Radius account has been reactivated. You can sign in and resume normal access.</p>
{render_button(href=dashboard_url, label="Open Dashboard")}
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)
