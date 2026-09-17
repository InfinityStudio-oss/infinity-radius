# ruff: noqa: E501
"""Shared HTML wrapper for every transactional email — plain inline-styled
HTML (no MJML/react-email build step), matching the project's philosophy
of not adding template-compiler tooling for a first pass. Table-based
layout for broad email-client compatibility. Long inline-CSS lines are
exempt from the line-length rule (E501) — wrapping HTML/CSS mid-attribute
would hurt readability more than it helps.
"""

import html

SUPPORT_EMAIL = "help@infinityradius.com"
GENERAL_EMAIL = "info@infinityradius.com"
PHONE_DISPLAY = "+255 747 730 270"


def render_email(*, app_url: str, preheader: str, body_html: str) -> str:
    logo_src = f"{app_url}/brand/infinity-radius-logo-full.png"
    return f"""\
<!doctype html>
<html>
  <head><meta charset="utf-8" /><meta name="viewport" content="width=device-width" /></head>
  <body style="margin:0;padding:0;background-color:#eef2f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <span style="display:none;font-size:0;line-height:0;max-height:0;max-width:0;opacity:0;overflow:hidden;">{html.escape(preheader)}</span>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef2f7;padding:40px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,0.06),0 8px 24px rgba(15,23,42,0.08);">
            <tr>
              <td bgcolor="#0891b2" style="height:5px;line-height:5px;font-size:0;background-color:#0891b2;">&nbsp;</td>
            </tr>
            <tr>
              <td style="padding:32px 32px 8px 32px;">
                <img src="{logo_src}" alt="Infinity Radius" height="40" style="height:40px;width:auto;display:block;" />
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px 32px 32px;color:#0f172a;font-size:15px;line-height:1.65;">
                {body_html}
              </td>
            </tr>
            <tr>
              <td style="padding:22px 32px;background-color:#f8fafc;border-top:1px solid #eef2f7;color:#94a3b8;font-size:12px;line-height:1.7;">
                Infinity Radius &mdash; Multi-tenant ISP billing, hotspot and WiFi management.<br />
                Support: <a href="mailto:{SUPPORT_EMAIL}" style="color:#2563eb;text-decoration:none;">{SUPPORT_EMAIL}</a>
                &nbsp;&middot;&nbsp;
                General: <a href="mailto:{GENERAL_EMAIL}" style="color:#2563eb;text-decoration:none;">{GENERAL_EMAIL}</a>
                &nbsp;&middot;&nbsp;
                Phone: {PHONE_DISPLAY}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def render_button(*, href: str, label: str) -> str:
    escaped_href = html.escape(href, quote=True)
    return f"""\
<a href="{escaped_href}" style="display:inline-block;background-color:#0f172a;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;padding:12px 24px;border-radius:8px;margin-top:8px;">{html.escape(label)}</a>
"""
