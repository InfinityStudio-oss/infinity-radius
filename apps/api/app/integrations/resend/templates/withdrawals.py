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
