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
<p style="margin:0 0 4px 0;color:#0891b2;font-size:13px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;">Withdrawal verification</p>
<p style="margin:0 0 24px 0;font-size:16px;">Confirm <strong>{_esc(tenant_name)}</strong>'s withdrawal of
<strong style="color:#151b2b;">{_esc(currency)} {amount:,.2f}</strong> to
<strong style="color:#151b2b;">{_esc(masked_destination)}</strong> with the code below.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px 0;">
  <tr>
    <td align="center" bgcolor="#151b2b" style="background-color:#151b2b;border-radius:16px;padding:28px 16px;">
      <span style="display:inline-block;font-family:'SF Mono',Consolas,Menlo,monospace;font-size:36px;font-weight:700;letter-spacing:10px;color:#ffffff;">{_esc(otp_display)}</span>
      <div style="margin-top:12px;font-size:12px;color:#22d3ee;font-weight:700;letter-spacing:0.05em;">EXPIRES IN {minutes} MINUTE{"S" if minutes != 1 else ""} &middot; SINGLE USE</div>
    </td>
  </tr>
</table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #eef2f7;padding-top:18px;">
  <tr>
    <td style="color:#64748b;font-size:13px;line-height:1.6;">
      &#128274;&nbsp; Infinity Radius will never ask you for this code by phone, chat, or email.
      If you did not request this withdrawal, contact support immediately and do not share this
      code with anyone.
    </td>
  </tr>
</table>
"""
    return subject, render_email(app_url=app_url, preheader=subject, body_html=body)
