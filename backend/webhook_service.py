"""
webhook_service.py — Outbound webhook delivery for Tether.

Each tenant can configure a webhook URL + secret. When significant events occur
(asset created/updated/deleted, request status change, warranty alert), this
module POSTs a signed JSON payload to that URL.

Signature: X-Tether-Signature header = "sha256=<hmac_hex>" where the HMAC is
computed over the raw JSON body using the tenant's webhook_secret.

Delivery is best-effort with up to 3 retries (exponential back-off).
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

_MAX_RETRIES = 3
_TIMEOUT     = 10  # seconds per attempt


def fire(tenant, event: str, payload: dict) -> bool:
    """
    Send a webhook to tenant.webhook_url if configured.

    Returns True if delivery succeeded, False otherwise.
    """
    if not tenant or not tenant.webhook_url:
        return False

    body = json.dumps({
        "event":      event,
        "tenant":     tenant.slug,
        "timestamp":  datetime.utcnow().isoformat() + "Z",
        "data":       payload,
    }, default=str).encode()

    headers = {"Content-Type": "application/json"}
    if tenant.webhook_secret:
        sig = hmac.new(tenant.webhook_secret.encode(), body, digestmod=hashlib.sha256).hexdigest()
        headers["X-Tether-Signature"] = f"sha256={sig}"

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            import urllib.request
            req = urllib.request.Request(tenant.webhook_url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                if 200 <= resp.status < 300:
                    log.info("Webhook %s → %s: %s", event, tenant.webhook_url, resp.status)
                    return True
                log.warning("Webhook %s attempt %d: HTTP %s", event, attempt, resp.status)
        except Exception as exc:
            log.warning("Webhook %s attempt %d failed: %s", event, attempt, exc)
        if attempt < _MAX_RETRIES:
            time.sleep(2 ** attempt)

    log.error("Webhook %s delivery failed after %d attempts", event, _MAX_RETRIES)
    return False
