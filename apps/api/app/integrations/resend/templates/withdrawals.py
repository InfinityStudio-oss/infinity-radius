# ruff: noqa: E501
"""Super Admin withdrawal-review email — sent only for withdrawals over
Settings.selcom_withdrawal_approval_threshold_tzs (see
app/services/payouts.py). Never includes an API key, private key,
provider credential, or unmasked destination account number.
"""

import html
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.integrations.resend.templates.base import render_button, render_email


def _esc(value: str | None) -> str:
    return html.escape(value) if value else "&mdash;"


def admin_withdrawal_review_email(
    *,
    app_url: str,
    withdrawal_id: UUID,
    tenant_name: str,
    amount: Decimal,
    currency: str,
    destination_channel: str,
    destination_code: str | None,
    masked_account: str | None,
    withdrawal_reference: str,
    requested_at: datetime,
) -> tuple[str, str]:
    subject = f"Withdrawal awaiting approval — {tenant_name} ({currency} {amount:,.2f})"
    review_url = f"{app_url}/super-admin/financial/disbursements?withdrawal={withdrawal_id}"
    rows = [
        ("Tenant", tenant_name),
        ("Amount", f"{currency} {amount:,.2f}"),
        ("Destination Type", destination_channel),
        ("Operator / Bank", destination_code),
        ("Destination Account", masked_account),
        ("Withdrawal Reference", withdrawal_reference),
        ("Requested At", requested_at.strftime("%Y-%m-%d %H:%M UTC")),
    ]
    table_rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748b;">{_esc(label)}</td>'
        f'<td style="padding:4px 0;color:#0f172a;font-weight:500;">{_esc(str(value) if value else None)}</td></tr>'
        for label, value in rows
    )
    body = f"""\
<p>A tenant withdrawal above the auto-approval threshold is awaiting your review.</p>
<table role="presentation" style="font-size:14px;margin-top:8px;">{table_rows}</table>
{render_button(href=review_url, label="Review Withdrawal")}
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)


def withdrawal_otp_email(
    *,
    app_url: str,
    tenant_name: str,
    amount: Decimal,
    currency: str,
    masked_destination: str,
    otp: str,
    ttl_seconds: int,
) -> tuple[str, str]:
    """The withdrawal 2FA code itself — the one email in this codebase
    that legitimately contains a live secret in its body. Never logged,
    never persisted (see app/services/payouts.py's EmailEvent write,
    which never includes the code), and this function's return value must
    never be logged either."""
    subject = "Infinity Radius Withdrawal Verification Code"
    minutes = max(1, ttl_seconds // 60)
    otp_display = " ".join(otp)  # "1 2 3 4 5 6" — easier to read/type correctly
    body = f"""\
<p>Use this verification code to confirm {_esc(tenant_name)}'s withdrawal of
{_esc(currency)} {amount:,.2f} to {_esc(masked_destination)}.</p>
<p style="text-align:center;margin:28px 0;">
  <span style="display:inline-block;font-size:32px;font-weight:700;letter-spacing:8px;
  color:#0f172a;background-color:#f1f5f9;border-radius:12px;padding:16px 24px;">{_esc(otp_display)}</span>
</p>
<p style="color:#64748b;font-size:13px;">This code expires in {minutes} minute{"s" if minutes != 1 else ""}
and can only be used once.</p>
<p style="color:#64748b;font-size:13px;">Infinity Radius will never ask you for this code by phone,
chat, or email. If you did not request this withdrawal, contact support immediately and do not
share this code with anyone.</p>
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)
