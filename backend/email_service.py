"""
email_service.py — Configurable email sending with white-label branding.

Configure via .env:

  EMAIL_PROVIDER=smtp        # smtp | resend | sendgrid | none (default)
  EMAIL_FROM=noreply@usetether.ca
  EMAIL_FROM_NAME=Tether

  # SMTP
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=you@gmail.com
  SMTP_PASSWORD=yourpassword
  SMTP_TLS=true              # true=STARTTLS, false=plain, ssl=SSL

  # Resend
  RESEND_API_KEY=re_xxx

  # SendGrid
  SENDGRID_API_KEY=SG.xxx

Set EMAIL_PROVIDER=none (or leave unset) to disable all email — Tether
will still work, but password reset links will only appear in the logs.
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from html import escape as _e
from typing import Optional

log = logging.getLogger(__name__)

EMAIL_PROVIDER  = os.environ.get("EMAIL_PROVIDER", "none").lower()
EMAIL_FROM      = os.environ.get("EMAIL_FROM", "noreply@usetether.ca")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Tether")
APP_URL         = os.environ.get("APP_URL", "https://usetether.ca")


def get_tenant_branding(tenant) -> dict:
    """Extract branding dict from a Tenant ORM object. Returns Tether defaults if None."""
    if not tenant:
        return {
            "brand_name":     "Tether",
            "brand_logo_url": "",
            "brand_accent":   "#d4f034",
            "brand_url":      APP_URL,
        }
    return {
        "brand_name":     tenant.email_from_name or tenant.name or "Tether",
        "brand_logo_url": tenant.email_logo_url or tenant.logo_url or "",
        "brand_accent":   tenant.email_accent_color or tenant.accent_color or "#d4f034",
        "brand_url":      APP_URL,
    }


def send_email(to: str, subject: str, html: str, text: Optional[str] = None,
               from_name: Optional[str] = None,
               from_address: Optional[str] = None) -> bool:
    """
    Send an email. Returns True on success, False on failure.
    Logs the content when provider=none so dev/test workflows still work.
    """
    effective_name    = from_name    or EMAIL_FROM_NAME
    effective_address = from_address or EMAIL_FROM

    if EMAIL_PROVIDER == "none":
        log.info(f"[email disabled] TO={to} SUBJECT={subject}\n{text or html}")
        return True

    try:
        if EMAIL_PROVIDER == "smtp":
            return _send_smtp(to, subject, html, text, effective_name, effective_address)
        elif EMAIL_PROVIDER == "resend":
            return _send_resend(to, subject, html, text, effective_name, effective_address)
        elif EMAIL_PROVIDER == "sendgrid":
            return _send_sendgrid(to, subject, html, text, effective_name, effective_address)
        else:
            log.warning(f"Unknown EMAIL_PROVIDER={EMAIL_PROVIDER!r}, email not sent")
            return False
    except Exception as exc:
        log.error(f"Email send failed to {to}: {exc}")
        return False


# ── SMTP ──────────────────────────────────────────────────────────────────────

def _send_smtp(to: str, subject: str, html: str, text: Optional[str],
               from_name: str, from_address: str) -> bool:
    host     = os.environ.get("SMTP_HOST", "localhost")
    port     = int(os.environ.get("SMTP_PORT", "587"))
    user     = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    tls_mode = os.environ.get("SMTP_TLS", "true").lower()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{from_address}>"
    msg["To"]      = to

    if text:
        msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    if tls_mode == "ssl":
        server = smtplib.SMTP_SSL(host, port)
    else:
        server = smtplib.SMTP(host, port)
        if tls_mode == "true":
            server.starttls()

    if user and password:
        server.login(user, password)

    server.sendmail(from_address, [to], msg.as_string())
    server.quit()
    log.info(f"SMTP email sent to {to}: {subject}")
    return True


# ── Resend ────────────────────────────────────────────────────────────────────

def _send_resend(to: str, subject: str, html: str, text: Optional[str],
                 from_name: str, from_address: str) -> bool:
    import urllib.request, json
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise ValueError("RESEND_API_KEY not set")

    payload = {
        "from":    f"{from_name} <{from_address}>",
        "to":      [to],
        "subject": subject,
        "html":    html,
    }
    if text:
        payload["text"] = text

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
        log.info(f"Resend email sent to {to}: id={body.get('id')}")
    return True


# ── SendGrid ──────────────────────────────────────────────────────────────────

def _send_sendgrid(to: str, subject: str, html: str, text: Optional[str],
                   from_name: str, from_address: str) -> bool:
    import urllib.request, json
    api_key = os.environ.get("SENDGRID_API_KEY", "")
    if not api_key:
        raise ValueError("SENDGRID_API_KEY not set")

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from":    {"email": from_address, "name": from_name},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}],
    }
    if text:
        payload["content"].insert(0, {"type": "text/plain", "value": text})

    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        log.info(f"SendGrid email sent to {to}: status={resp.status}")
    return True


# ── Email templates ───────────────────────────────────────────────────────────

def _base_template(title: str, body: str, *,
                   brand_name: str = "Tether",
                   brand_logo_url: str = "",
                   brand_accent: str = "#d4f034",
                   brand_url: str = "") -> str:
    """Minimal, clean HTML email template with white-label branding support."""
    brand_url = brand_url or APP_URL

    if brand_logo_url:
        logo_html = (
            f'<img src="{_e(brand_logo_url)}" alt="{_e(brand_name)}" '
            f'style="max-height:36px;max-width:160px;object-fit:contain;display:block;">'
        )
    else:
        logo_html = (
            f'<table cellpadding="0" cellspacing="0">'
            f'<tr>'
            f'<td style="background:#21242c;border:1px solid #2e3340;border-radius:8px;'
            f'width:32px;height:32px;text-align:center;vertical-align:middle;">'
            f'<span style="color:{_e(brand_accent)};font-size:18px;font-weight:900;line-height:32px;">+</span>'
            f'</td>'
            f'<td style="padding-left:10px;color:#ffffff;font-size:18px;font-weight:700;'
            f'letter-spacing:-.02em;">{_e(brand_name)}</td>'
            f'</tr>'
            f'</table>'
        )

    # Derive a readable domain for the footer link
    try:
        from urllib.parse import urlparse
        display_url = urlparse(brand_url).netloc or brand_url
    except Exception:
        display_url = brand_url

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title>
</head>
<body style="margin:0;padding:0;background:#f5f6f8;font-family:'IBM Plex Sans',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f6f8;padding:40px 20px;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">

      <!-- Header -->
      <tr><td style="background:#15171c;border-radius:12px 12px 0 0;padding:28px 36px;border-bottom:1px solid #2e3340;">
        {logo_html}
      </td></tr>

      <!-- Body -->
      <tr><td style="background:#1a1d24;padding:36px;border-left:1px solid #2e3340;border-right:1px solid #2e3340;">
        {body}
      </td></tr>

      <!-- Footer -->
      <tr><td style="background:#15171c;border-radius:0 0 12px 12px;padding:20px 36px;border:1px solid #2e3340;border-top:none;text-align:center;">
        <p style="margin:0;color:#4b5563;font-size:12px;">
          {_e(brand_name)} &nbsp;&middot;&nbsp;
          <a href="{_e(brand_url)}" style="color:#6b7280;text-decoration:none;">{_e(display_url)}</a>
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def send_password_reset(to: str, name: str, reset_url: str, *, tenant=None) -> bool:
    branding = get_tenant_branding(tenant)
    accent   = branding["brand_accent"]
    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">Reset your password</h2>
    <p style="color:#9ca3af;margin:0 0 24px;line-height:1.7;">
      Hi {_e(name)}, we received a request to reset the password for your account.
      Click the button below to choose a new password.
    </p>
    <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr><td style="background:{_e(accent)};border-radius:8px;">
        <a href="{_e(reset_url)}" style="display:inline-block;padding:13px 28px;color:#15171c;font-weight:700;font-size:15px;text-decoration:none;border-radius:8px;">
          Reset password
        </a>
      </td></tr>
    </table>
    <p style="color:#6b7280;font-size:13px;margin:0 0 8px;">
      This link expires in <strong style="color:#9ca3af;">1 hour</strong>.
      If you didn't request a password reset, you can safely ignore this email.
    </p>
    <p style="color:#4b5563;font-size:12px;margin:0;word-break:break-all;">
      Or copy this URL: <a href="{_e(reset_url)}" style="color:{_e(accent)};">{_e(reset_url)}</a>
    </p>"""

    text = f"""Reset your password

Hi {name},

Click this link to reset your password (expires in 1 hour):
{reset_url}

If you didn't request a password reset, ignore this email.
"""
    return send_email(
        to, "Reset your password",
        _base_template("Reset your password", html_body, **branding),
        text,
        from_name=tenant.email_from_name if tenant else None,
        from_address=tenant.email_from_address if tenant else None,
    )


def send_welcome(to: str, name: str, login_url: str, role: str, *, tenant=None) -> bool:
    branding = get_tenant_branding(tenant)
    accent   = branding["brand_accent"]
    brand    = branding["brand_name"]
    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">Welcome to {_e(brand)}</h2>
    <p style="color:#9ca3af;margin:0 0 24px;line-height:1.7;">
      Hi {_e(name)}, your account has been created with the role
      <strong style="color:{_e(accent)};">{_e(role.replace('_', ' ').title())}</strong>.
      Click below to log in.
    </p>
    <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr><td style="background:{_e(accent)};border-radius:8px;">
        <a href="{_e(login_url)}" style="display:inline-block;padding:13px 28px;color:#15171c;font-weight:700;font-size:15px;text-decoration:none;border-radius:8px;">
          Log in
        </a>
      </td></tr>
    </table>"""

    text = f"""Welcome to {brand}, {name}!

Your account has been created. Log in here:
{login_url}
"""
    return send_email(
        to, f"Welcome to {brand}",
        _base_template(f"Welcome to {brand}", html_body, **branding),
        text,
        from_name=tenant.email_from_name if tenant else None,
        from_address=tenant.email_from_address if tenant else None,
    )


def send_invite(to: str, name: str, invite_url: str, tenant_name: str, role: str,
                *, tenant=None) -> bool:
    branding = get_tenant_branding(tenant)
    accent   = branding["brand_accent"]
    brand    = branding["brand_name"]
    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">You've been invited</h2>
    <p style="color:#9ca3af;margin:0 0 24px;line-height:1.7;">
      Hi {_e(name)}, you've been invited to join <strong style="color:#ffffff;">{_e(tenant_name)}</strong>
      as a <strong style="color:{_e(accent)};">{_e(role.replace('_',' ').title())}</strong>.
      Click below to accept and set your password.
    </p>
    <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr><td style="background:{_e(accent)};border-radius:8px;">
        <a href="{_e(invite_url)}" style="display:inline-block;padding:13px 28px;color:#15171c;font-weight:700;font-size:15px;text-decoration:none;border-radius:8px;">
          Accept invitation
        </a>
      </td></tr>
    </table>
    <p style="color:#6b7280;font-size:13px;margin:0;">
      This invitation expires in 7 days. If you weren't expecting this, ignore it.
    </p>"""

    text = f"""You've been invited to {tenant_name}

Hi {name},

Accept your invitation here (expires in 7 days):
{invite_url}
"""
    return send_email(
        to, f"You're invited to join {tenant_name}",
        _base_template("You've been invited", html_body, **branding),
        text,
        from_name=tenant.email_from_name if tenant else None,
        from_address=tenant.email_from_address if tenant else None,
    )


_PRIORITY_COLOURS = {
    "urgent": "#ef4444",
    "high":   "#f59e0b",
    "normal": "#3b82f6",
    "low":    "#9ca3af",
}

_STATUS_LABELS = {
    "open":        "Open",
    "in_progress": "In Progress",
    "fulfilled":   "Fulfilled",
    "declined":    "Declined",
}

_STATUS_COLOURS = {
    "fulfilled":   "#10b981",
    "declined":    "#ef4444",
    "in_progress": "#f59e0b",
    "open":        "#3b82f6",
}


def send_request_notification(
    to: str, name: str,
    tenant_name: str, requester_name: str,
    title: str, description: str,
    priority: str, view_url: str,
) -> bool:
    """Notify MSP staff that a new asset request was submitted."""
    priority_colour = _PRIORITY_COLOURS.get(priority, "#9ca3af")
    desc_short = (description[:200] + "…") if len(description) > 200 else description

    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">New asset request</h2>
    <p style="color:#9ca3af;margin:0 0 20px;line-height:1.7;">
      Hi {_e(name)}, a new request has been submitted by
      <strong style="color:#ffffff;">{_e(requester_name)}</strong>
      from <strong style="color:#ffffff;">{_e(tenant_name)}</strong>.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#15171c;border:1px solid #2e3340;border-radius:8px;margin-bottom:24px;">
      <tr>
        <td style="padding:16px 20px;border-bottom:1px solid #2e3340;">
          <div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;">Title</div>
          <div style="color:#ffffff;font-size:15px;font-weight:600;">{_e(title)}</div>
        </td>
      </tr>
      <tr>
        <td style="padding:16px 20px;border-bottom:1px solid #2e3340;">
          <div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;">Priority</div>
          <span style="display:inline-block;padding:3px 10px;background:{_e(priority_colour)}22;
                       color:{_e(priority_colour)};border-radius:4px;font-size:13px;font-weight:600;">
            {_e(priority.title())}
          </span>
        </td>
      </tr>
      {f'<tr><td style="padding:16px 20px;"><div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;">Details</div><div style="color:#c9cdd6;font-size:14px;line-height:1.6;">{_e(desc_short)}</div></td></tr>' if desc_short else ''}
    </table>
    <table cellpadding="0" cellspacing="0">
      <tr><td style="background:#d4f034;border-radius:8px;">
        <a href="{_e(view_url)}" style="display:inline-block;padding:13px 28px;color:#15171c;
                font-weight:700;font-size:15px;text-decoration:none;border-radius:8px;">
          View request
        </a>
      </td></tr>
    </table>"""

    text = f"""New asset request — {tenant_name}

Hi {name},

{requester_name} from {tenant_name} submitted a new request.

Title:    {title}
Priority: {priority}
{('Details:  ' + desc_short) if desc_short else ''}

View it here: {view_url}
"""
    return send_email(
        to,
        f"New asset request from {tenant_name} — {title}",
        _base_template("New asset request", html_body),
        text,
    )


def send_request_update(
    to: str, name: str,
    title: str, new_status: str,
    notes: str, view_url: str,
    *, tenant=None,
) -> bool:
    """Notify a client user that their request status changed."""
    branding       = get_tenant_branding(tenant)
    accent         = branding["brand_accent"]
    status_label   = _STATUS_LABELS.get(new_status, new_status.replace("_", " ").title())
    status_colour  = _STATUS_COLOURS.get(new_status, "#9ca3af")

    notes_section = ""
    if notes:
        notes_section = f"""
    <div style="background:#15171c;border-left:3px solid {_e(accent)};border-radius:0 6px 6px 0;
                padding:16px 20px;margin-bottom:24px;">
      <div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;">
        Response from your MSP
      </div>
      <div style="color:#c9cdd6;font-size:14px;line-height:1.6;">{_e(notes)}</div>
    </div>"""

    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">Request updated</h2>
    <p style="color:#9ca3af;margin:0 0 20px;line-height:1.7;">
      Hi {_e(name)}, your request has been updated.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#15171c;border:1px solid #2e3340;border-radius:8px;margin-bottom:24px;">
      <tr>
        <td style="padding:16px 20px;border-bottom:1px solid #2e3340;">
          <div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;">Request</div>
          <div style="color:#ffffff;font-size:15px;font-weight:600;">{_e(title)}</div>
        </td>
      </tr>
      <tr>
        <td style="padding:16px 20px;">
          <div style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;">New status</div>
          <span style="display:inline-block;padding:3px 10px;background:{_e(status_colour)}22;
                       color:{_e(status_colour)};border-radius:4px;font-size:13px;font-weight:600;">
            {_e(status_label)}
          </span>
        </td>
      </tr>
    </table>
    {notes_section}
    <table cellpadding="0" cellspacing="0">
      <tr><td style="background:{_e(accent)};border-radius:8px;">
        <a href="{_e(view_url)}" style="display:inline-block;padding:13px 28px;color:#15171c;
                font-weight:700;font-size:15px;text-decoration:none;border-radius:8px;">
          View request
        </a>
      </td></tr>
    </table>"""

    notes_text = f"\nResponse from your MSP:\n{notes}\n" if notes else ""
    text = f"""Your request has been updated — {title}

Hi {name},

Your request "{title}" has been updated to: {status_label}
{notes_text}
View it here: {view_url}
"""
    return send_email(
        to,
        f"Your request has been updated — {title}",
        _base_template("Request updated", html_body, **branding),
        text,
        from_name=tenant.email_from_name if tenant else None,
        from_address=tenant.email_from_address if tenant else None,
    )


def send_warranty_alert(to: str, name: str, tenant_name: str,
                        expiring: list, login_url: str, *, tenant=None) -> bool:
    branding = get_tenant_branding(tenant)
    accent   = branding["brand_accent"]
    rows = "".join(
        f'<tr>'
        f'<td style="padding:10px 14px;border-bottom:1px solid #2e3340;color:#c9cdd6;font-size:14px;">{_e(a["asset_tag"])}</td>'
        f'<td style="padding:10px 14px;border-bottom:1px solid #2e3340;color:#c9cdd6;font-size:14px;">{_e(a["name"])}</td>'
        f'<td style="padding:10px 14px;border-bottom:1px solid #2e3340;color:#f59e0b;font-size:14px;font-weight:600;">{_e(str(a["warranty_expiry"]))}</td>'
        f'</tr>'
        for a in expiring
    )
    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">
      Warranties expiring soon
    </h2>
    <p style="color:#9ca3af;margin:0 0 20px;line-height:1.7;">
      Hi {_e(name)}, the following assets in <strong style="color:#ffffff;">{_e(tenant_name)}</strong>
      have warranties expiring within the next 30 days.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#15171c;border:1px solid #2e3340;border-radius:8px;overflow:hidden;margin-bottom:24px;">
      <thead>
        <tr style="background:#21242c;">
          <th style="padding:10px 14px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Tag</th>
          <th style="padding:10px 14px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Asset</th>
          <th style="padding:10px 14px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Expires</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <table cellpadding="0" cellspacing="0">
      <tr><td style="background:{_e(accent)};border-radius:8px;">
        <a href="{_e(login_url)}" style="display:inline-block;padding:12px 24px;color:#15171c;font-weight:700;font-size:14px;text-decoration:none;border-radius:8px;">
          View assets
        </a>
      </td></tr>
    </table>"""

    items = "\n".join(f"  - {a['asset_tag']} {a['name']} (expires {a['warranty_expiry']})" for a in expiring)
    text = f"""Warranties expiring soon — {tenant_name}

Hi {name},

{len(expiring)} asset(s) have warranties expiring within 30 days:

{items}

Log in to view: {login_url}
"""
    return send_email(
        to, f"Warranty alert — {len(expiring)} asset(s) expiring soon",
        _base_template("Warranties expiring soon", html_body, **branding),
        text,
        from_name=tenant.email_from_name if tenant else None,
        from_address=tenant.email_from_address if tenant else None,
    )


def send_licence_expiry_alert(to: str, name: str,
                               expiring: list, login_url: str) -> bool:
    """Notify MSP admins about software licences expiring soon."""
    rows = "".join(
        f'<tr>'
        f'<td style="padding:10px 14px;border-bottom:1px solid #2e3340;color:#c9cdd6;font-size:14px;">{_e(lic["tenant"])}</td>'
        f'<td style="padding:10px 14px;border-bottom:1px solid #2e3340;color:#c9cdd6;font-size:14px;">{_e(lic["name"])}</td>'
        f'<td style="padding:10px 14px;border-bottom:1px solid #2e3340;color:#c9cdd6;font-size:14px;">{_e(lic["vendor"])}</td>'
        f'<td style="padding:10px 14px;border-bottom:1px solid #2e3340;color:#f59e0b;font-size:14px;font-weight:600;">{_e(str(lic["expiry_date"]))}</td>'
        f'</tr>'
        for lic in expiring
    )
    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">
      Software licences expiring soon
    </h2>
    <p style="color:#9ca3af;margin:0 0 20px;line-height:1.7;">
      Hi {_e(name)}, the following software licences are expiring within the alert window.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#15171c;border:1px solid #2e3340;border-radius:8px;overflow:hidden;margin-bottom:24px;">
      <thead>
        <tr style="background:#21242c;">
          <th style="padding:10px 14px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Client</th>
          <th style="padding:10px 14px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Licence</th>
          <th style="padding:10px 14px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Vendor</th>
          <th style="padding:10px 14px;text-align:left;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.06em;">Expires</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <table cellpadding="0" cellspacing="0">
      <tr><td style="background:#d4f034;border-radius:8px;">
        <a href="{_e(login_url)}" style="display:inline-block;padding:12px 24px;color:#15171c;font-weight:700;font-size:14px;text-decoration:none;border-radius:8px;">
          View licences
        </a>
      </td></tr>
    </table>"""

    items = "\n".join(
        f"  - [{lic['tenant']}] {lic['name']} ({lic['vendor']}) — expires {lic['expiry_date']}"
        for lic in expiring
    )
    text = f"""Software licences expiring soon

Hi {name},

{len(expiring)} licence(s) are expiring soon:

{items}

Log in to view: {login_url}
"""
    return send_email(
        to, f"Licence alert — {len(expiring)} licence(s) expiring soon",
        _base_template("Licences expiring soon", html_body),
        text,
    )
