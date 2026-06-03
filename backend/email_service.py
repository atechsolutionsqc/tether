"""
email_service.py — Configurable email sending.

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


def _from_header() -> str:
    return f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"


def send_email(to: str, subject: str, html: str, text: Optional[str] = None) -> bool:
    """
    Send an email. Returns True on success, False on failure.
    Logs the content when provider=none so dev/test workflows still work.
    """
    if EMAIL_PROVIDER == "none":
        log.info(f"[email disabled] TO={to} SUBJECT={subject}\n{text or html}")
        return True

    try:
        if EMAIL_PROVIDER == "smtp":
            return _send_smtp(to, subject, html, text)
        elif EMAIL_PROVIDER == "resend":
            return _send_resend(to, subject, html, text)
        elif EMAIL_PROVIDER == "sendgrid":
            return _send_sendgrid(to, subject, html, text)
        else:
            log.warning(f"Unknown EMAIL_PROVIDER={EMAIL_PROVIDER!r}, email not sent")
            return False
    except Exception as exc:
        log.error(f"Email send failed to {to}: {exc}")
        return False


# ── SMTP ──────────────────────────────────────────────────────────────────────

def _send_smtp(to: str, subject: str, html: str, text: Optional[str]) -> bool:
    host     = os.environ.get("SMTP_HOST", "localhost")
    port     = int(os.environ.get("SMTP_PORT", "587"))
    user     = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    tls_mode = os.environ.get("SMTP_TLS", "true").lower()   # true | false | ssl

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = _from_header()
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

    server.sendmail(EMAIL_FROM, [to], msg.as_string())
    server.quit()
    log.info(f"SMTP email sent to {to}: {subject}")
    return True


# ── Resend ────────────────────────────────────────────────────────────────────

def _send_resend(to: str, subject: str, html: str, text: Optional[str]) -> bool:
    import urllib.request, json
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise ValueError("RESEND_API_KEY not set")

    payload = {
        "from":    _from_header(),
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

def _send_sendgrid(to: str, subject: str, html: str, text: Optional[str]) -> bool:
    import urllib.request, json
    api_key = os.environ.get("SENDGRID_API_KEY", "")
    if not api_key:
        raise ValueError("SENDGRID_API_KEY not set")

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from":    {"email": EMAIL_FROM, "name": EMAIL_FROM_NAME},
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

def _base_template(title: str, body: str) -> str:
    """Minimal, clean HTML email template matching Tether brand."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f5f6f8;font-family:'IBM Plex Sans',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f6f8;padding:40px 20px;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">

      <!-- Header -->
      <tr><td style="background:#15171c;border-radius:12px 12px 0 0;padding:28px 36px;border-bottom:1px solid #2e3340;">
        <table cellpadding="0" cellspacing="0">
          <tr>
            <td style="background:#21242c;border:1px solid #2e3340;border-radius:8px;width:32px;height:32px;text-align:center;vertical-align:middle;">
              <span style="color:#d4f034;font-size:18px;font-weight:900;line-height:32px;">+</span>
            </td>
            <td style="padding-left:10px;color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-.02em;">Tether</td>
          </tr>
        </table>
      </td></tr>

      <!-- Body -->
      <tr><td style="background:#1a1d24;padding:36px;border-left:1px solid #2e3340;border-right:1px solid #2e3340;">
        {body}
      </td></tr>

      <!-- Footer -->
      <tr><td style="background:#15171c;border-radius:0 0 12px 12px;padding:20px 36px;border:1px solid #2e3340;border-top:none;text-align:center;">
        <p style="margin:0;color:#4b5563;font-size:12px;">
          Tether by ATech Solutions &nbsp;&middot;&nbsp;
          <a href="{APP_URL}" style="color:#6b7280;text-decoration:none;">usetether.ca</a>
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def send_password_reset(to: str, name: str, reset_url: str) -> bool:
    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">Reset your password</h2>
    <p style="color:#9ca3af;margin:0 0 24px;line-height:1.7;">
      Hi {name}, we received a request to reset the password for your Tether account.
      Click the button below to choose a new password.
    </p>
    <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr><td style="background:#d4f034;border-radius:8px;">
        <a href="{reset_url}" style="display:inline-block;padding:13px 28px;color:#15171c;font-weight:700;font-size:15px;text-decoration:none;border-radius:8px;">
          Reset password
        </a>
      </td></tr>
    </table>
    <p style="color:#6b7280;font-size:13px;margin:0 0 8px;">
      This link expires in <strong style="color:#9ca3af;">1 hour</strong>.
      If you didn't request a password reset, you can safely ignore this email.
    </p>
    <p style="color:#4b5563;font-size:12px;margin:0;word-break:break-all;">
      Or copy this URL: <a href="{reset_url}" style="color:#d4f034;">{reset_url}</a>
    </p>"""

    text = f"""Reset your Tether password

Hi {name},

Click this link to reset your password (expires in 1 hour):
{reset_url}

If you didn't request a password reset, ignore this email.
"""
    return send_email(to, "Reset your Tether password", _base_template("Reset your password", html_body), text)


def send_welcome(to: str, name: str, login_url: str, role: str) -> bool:
    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">Welcome to Tether</h2>
    <p style="color:#9ca3af;margin:0 0 24px;line-height:1.7;">
      Hi {_e(name)}, your Tether account has been created with the role
      <strong style="color:#d4f034;">{_e(role.replace('_', ' ').title())}</strong>.
      Click below to log in.
    </p>
    <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr><td style="background:#d4f034;border-radius:8px;">
        <a href="{_e(login_url)}" style="display:inline-block;padding:13px 28px;color:#15171c;font-weight:700;font-size:15px;text-decoration:none;border-radius:8px;">
          Log in to Tether
        </a>
      </td></tr>
    </table>
    <p style="color:#6b7280;font-size:13px;margin:0;">
      Need help? Email <a href="mailto:support@usetether.ca" style="color:#d4f034;">support@usetether.ca</a>
    </p>"""

    text = f"""Welcome to Tether, {name}!

Your account has been created. Log in here:
{login_url}

Need help? Email support@usetether.ca
"""
    return send_email(to, "Welcome to Tether", _base_template("Welcome to Tether", html_body), text)


def send_invite(to: str, name: str, invite_url: str, tenant_name: str, role: str) -> bool:
    html_body = f"""
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px;font-weight:700;">You've been invited</h2>
    <p style="color:#9ca3af;margin:0 0 24px;line-height:1.7;">
      Hi {_e(name)}, you've been invited to join <strong style="color:#ffffff;">{_e(tenant_name)}</strong>
      on Tether as a <strong style="color:#d4f034;">{_e(role.replace('_',' ').title())}</strong>.
      Click below to accept and set your password.
    </p>
    <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr><td style="background:#d4f034;border-radius:8px;">
        <a href="{_e(invite_url)}" style="display:inline-block;padding:13px 28px;color:#15171c;font-weight:700;font-size:15px;text-decoration:none;border-radius:8px;">
          Accept invitation
        </a>
      </td></tr>
    </table>
    <p style="color:#6b7280;font-size:13px;margin:0;">
      This invitation expires in 7 days. If you weren't expecting this, ignore it.
    </p>"""

    text = f"""You've been invited to {tenant_name} on Tether

Hi {name},

Accept your invitation here (expires in 7 days):
{invite_url}
"""
    return send_email(to, f"You're invited to {tenant_name} on Tether",
                      _base_template("You've been invited", html_body), text)


def send_warranty_alert(to: str, name: str, tenant_name: str,
                        expiring: list, login_url: str) -> bool:
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
      <tr><td style="background:#d4f034;border-radius:8px;">
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
    return send_email(to, f"Warranty alert — {len(expiring)} asset(s) expiring soon",
                      _base_template("Warranties expiring soon", html_body), text)
