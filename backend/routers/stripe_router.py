"""
routers/stripe_router.py

Stripe integration for Tether SaaS.

Endpoints:
  GET  /api/stripe/config         — public price IDs + publishable key for frontend
  POST /api/stripe/checkout       — create Checkout Session for upgrade
  POST /api/stripe/portal         — create Customer Portal session (manage/cancel)
  POST /api/stripe/webhook        — Stripe webhook receiver (must be public, no auth)

Environment variables required:
  STRIPE_SECRET_KEY
  STRIPE_PUBLISHABLE_KEY
  STRIPE_WEBHOOK_SECRET
  STRIPE_PRICE_STARTER_MONTHLY
  STRIPE_PRICE_STARTER_ANNUAL
  STRIPE_PRICE_GROWTH_MONTHLY
  STRIPE_PRICE_GROWTH_ANNUAL
  STRIPE_PRICE_SCALE_MONTHLY
  STRIPE_PRICE_SCALE_ANNUAL
  APP_URL  (e.g. https://usetether.ca)

Stripe webhook events handled:
  checkout.session.completed       → activate tier
  customer.subscription.updated    → update tier / interval
  customer.subscription.deleted    → downgrade to trial
  invoice.payment_failed           → log (email handled by Stripe)
"""
import os
import logging
from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from models.models import MspBilling, User
from billing import TIERS, TIER_ORDER, is_saas
from security import get_current_user, CurrentUser

log = logging.getLogger(__name__)
router = APIRouter()

# ── Stripe client setup ────────────────────────────────────────────────────────
STRIPE_SECRET_KEY    = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
APP_URL              = os.environ.get("APP_URL", "https://usetether.ca")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ── Price ID map ───────────────────────────────────────────────────────────────
# Maps (tier_key, interval) → Stripe Price ID from env
PRICE_MAP = {
    ("starter", "monthly"): os.environ.get("STRIPE_PRICE_STARTER_MONTHLY", ""),
    ("starter", "annual"):  os.environ.get("STRIPE_PRICE_STARTER_ANNUAL", ""),
    ("growth",  "monthly"): os.environ.get("STRIPE_PRICE_GROWTH_MONTHLY", ""),
    ("growth",  "annual"):  os.environ.get("STRIPE_PRICE_GROWTH_ANNUAL", ""),
    ("scale",   "monthly"): os.environ.get("STRIPE_PRICE_SCALE_MONTHLY", ""),
    ("scale",   "annual"):  os.environ.get("STRIPE_PRICE_SCALE_ANNUAL", ""),
}

# Reverse map: Stripe Price ID → (tier_key, interval)
PRICE_TO_TIER = {v: k for k, v in PRICE_MAP.items() if v}

def _stripe_enabled() -> bool:
    return bool(STRIPE_SECRET_KEY)

def _require_stripe():
    if not _stripe_enabled():
        raise HTTPException(503, "Stripe is not configured on this installation.")

def _billing_row(db: Session) -> MspBilling:
    row = db.query(MspBilling).first()
    if not row:
        row = MspBilling(tier="trial" if is_saas() else "selfhosted")
        db.add(row); db.commit(); db.refresh(row)
    return row


# ── GET /config — public price IDs for the frontend ──────────────────────────

@router.get("/config")
def stripe_config():
    """Public endpoint — returns publishable key and price IDs for the frontend."""
    return {
        "enabled":          _stripe_enabled(),
        "publishable_key":  os.environ.get("STRIPE_PUBLISHABLE_KEY", ""),
        "prices": {
            "starter_monthly": PRICE_MAP.get(("starter", "monthly"), ""),
            "starter_annual":  PRICE_MAP.get(("starter", "annual"), ""),
            "growth_monthly":  PRICE_MAP.get(("growth",  "monthly"), ""),
            "growth_annual":   PRICE_MAP.get(("growth",  "annual"), ""),
            "scale_monthly":   PRICE_MAP.get(("scale",   "monthly"), ""),
            "scale_annual":    PRICE_MAP.get(("scale",   "annual"), ""),
        },
    }


# ── POST /checkout — create Stripe Checkout Session ──────────────────────────

class CheckoutRequest(BaseModel):
    tier:     str   # starter | growth | scale
    interval: str   # monthly | annual


@router.post("/checkout")
def create_checkout(
    body:  CheckoutRequest,
    db:    Session = Depends(get_db),
    cu:    CurrentUser = Depends(get_current_user),
):
    cu.require("msp.dashboard")
    _require_stripe()

    if body.tier not in ("starter", "growth", "scale"):
        raise HTTPException(400, "Invalid tier. Choose starter, growth, or scale.")
    if body.interval not in ("monthly", "annual"):
        raise HTTPException(400, "Invalid interval. Choose monthly or annual.")

    price_id = PRICE_MAP.get((body.tier, body.interval), "")
    if not price_id:
        raise HTTPException(503, f"Price not configured for {body.tier}/{body.interval}. "
                                 f"Set STRIPE_PRICE_{body.tier.upper()}_{body.interval.upper()} in your .env")

    row = _billing_row(db)

    # Create or reuse Stripe customer
    customer_id = row.stripe_customer_id
    if not customer_id:
        user = db.query(User).filter(User.id == cu.id).first()
        customer = stripe.Customer.create(
            email=user.email if user else row.billing_email,
            name=row.msp_name or (user.name if user else ""),
            metadata={"tether_billing_id": str(row.id)},
        )
        customer_id = customer.id
        row.stripe_customer_id = customer_id
        db.commit()

    # Determine if this is an upgrade (existing subscription)
    if row.stripe_subscription_id:
        # Modify existing subscription via portal instead
        raise HTTPException(400, "You already have an active subscription. "
                                 "Use the Customer Portal to change your plan.")

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        subscription_data={
            "metadata": {
                "tether_tier":     body.tier,
                "tether_interval": body.interval,
            },
        },
        success_url=f"{APP_URL}/billing?session={{CHECKOUT_SESSION_ID}}&success=1",
        cancel_url=f"{APP_URL}/billing?cancelled=1",
        allow_promotion_codes=True,
        billing_address_collection="required",
    )

    return {"checkout_url": session.url, "session_id": session.id}


# ── POST /portal — Stripe Customer Portal ────────────────────────────────────

@router.post("/portal")
def create_portal(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
):
    """Create a Stripe Customer Portal session so customers can manage/cancel."""
    cu.require("msp.dashboard")
    _require_stripe()

    row = _billing_row(db)
    if not row.stripe_customer_id:
        raise HTTPException(400, "No Stripe customer found. Complete a checkout first.")

    session = stripe.billing_portal.Session.create(
        customer=row.stripe_customer_id,
        return_url=f"{APP_URL}/billing",
    )
    return {"portal_url": session.url}


# ── POST /webhook — Stripe webhook receiver ───────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe sends events here. Must be registered in the Stripe dashboard.
    The endpoint must be publicly accessible (no auth header).

    Stripe Dashboard → Developers → Webhooks → Add endpoint:
      URL: https://usetether.ca/api/stripe/webhook
      Events: checkout.session.completed, customer.subscription.updated,
              customer.subscription.deleted, invoice.payment_failed
    """
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:
            log.warning("Stripe webhook signature verification failed")
            raise HTTPException(400, "Invalid signature")
    else:
        # Dev/test mode — accept without verification (log warning)
        import json
        log.warning("STRIPE_WEBHOOK_SECRET not set — accepting webhook without verification")
        event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)

    etype = event["type"]
    data  = event["data"]["object"]
    log.info(f"Stripe webhook: {etype}")

    row = db.query(MspBilling).first()
    if not row:
        return Response(status_code=200)

    try:
        if etype == "checkout.session.completed":
            _handle_checkout_completed(data, row, db)

        elif etype == "customer.subscription.updated":
            _handle_subscription_updated(data, row, db)

        elif etype == "customer.subscription.deleted":
            _handle_subscription_deleted(data, row, db)

        elif etype == "invoice.payment_failed":
            log.warning(f"Payment failed for customer {data.get('customer')} — Stripe will retry")

    except Exception as exc:
        log.error(f"Webhook handler error ({etype}): {exc}", exc_info=True)
        # Return 200 anyway — Stripe shouldn't retry on app errors
        return Response(status_code=200)

    return Response(status_code=200)


# ── Webhook event handlers ────────────────────────────────────────────────────

def _handle_checkout_completed(session, row: MspBilling, db: Session):
    """Checkout completed → activate the subscription tier."""
    if session.get("mode") != "subscription":
        return

    sub_id = session.get("subscription")
    if not sub_id:
        return

    # Fetch the subscription to get the price ID
    sub = stripe.Subscription.retrieve(sub_id)
    _apply_subscription(sub, row, db)

    log.info(f"Checkout completed → tier={row.tier} interval={row.billing_interval}")

    # Send upgrade confirmation email
    try:
        from email_service import send_email, _base_template, APP_URL
        if row.billing_email:
            tier_name = TIERS.get(row.tier, {}).get("name", row.tier.title())
            html = f"""
            <h2 style="color:#fff;font-size:22px;margin:0 0 12px;">You\'re on {tier_name}!</h2>
            <p style="color:#9ca3af;margin:0 0 20px;line-height:1.7;">
              Your Tether subscription is now active. Your asset limit has been updated.
            </p>
            <table cellpadding="0" cellspacing="0">
              <tr><td style="background:#d4f034;border-radius:8px;">
                <a href="{APP_URL}" style="display:inline-block;padding:12px 24px;color:#15171c;font-weight:700;font-size:14px;text-decoration:none;">
                  Open Tether
                </a>
              </td></tr>
            </table>"""
            send_email(
                row.billing_email,
                f"You're now on the {tier_name} plan — Tether",
                _base_template(f"You\'re on {tier_name}!", html),
            )
    except Exception as e:
        log.warning(f"Failed to send upgrade email: {e}")


def _handle_subscription_updated(sub, row: MspBilling, db: Session):
    """Subscription changed (plan switch, renewal, etc.) → sync tier."""
    _apply_subscription(sub, row, db)
    log.info(f"Subscription updated → tier={row.tier} interval={row.billing_interval}")


def _handle_subscription_deleted(sub, row: MspBilling, db: Session):
    """Subscription cancelled → downgrade to trial (or expired trial)."""
    row.tier                   = "trial"
    row.billing_interval       = "monthly"
    row.stripe_subscription_id = None
    row.stripe_price_id        = None
    row.trial_ends_at          = None   # mark as expired trial
    row.updated_at             = datetime.utcnow()
    db.commit()
    log.info("Subscription deleted → reverted to trial (expired)")


def _apply_subscription(sub, row: MspBilling, db: Session):
    """Extract tier/interval from a Stripe subscription object and save."""
    # Get price ID from subscription items
    items = sub.get("items", {}).get("data", [])
    if not items:
        return

    price_id = items[0]["price"]["id"]
    tier_key, interval = PRICE_TO_TIER.get(price_id, ("starter", "monthly"))

    row.tier                   = tier_key
    row.billing_interval       = interval
    row.stripe_subscription_id = sub["id"]
    row.stripe_customer_id     = sub.get("customer", row.stripe_customer_id)
    row.stripe_price_id        = price_id
    row.trial_ends_at          = None   # clear trial once paid
    row.updated_at             = datetime.utcnow()
    db.commit()


# ── GET /subscription — current subscription details ─────────────────────────

@router.get("/subscription")
def subscription_details(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
):
    cu.require("msp.dashboard")
    row = _billing_row(db)
    has_sub = bool(row.stripe_subscription_id)

    details = {
        "has_subscription":    has_sub,
        "tier":                row.tier,
        "billing_interval":    row.billing_interval,
        "stripe_customer_id":  row.stripe_customer_id,
        "stripe_enabled":      _stripe_enabled(),
        "can_manage":          has_sub and _stripe_enabled(),
    }

    if has_sub and _stripe_enabled():
        try:
            sub = stripe.Subscription.retrieve(row.stripe_subscription_id)
            details["current_period_end"] = datetime.fromtimestamp(
                sub["current_period_end"]
            ).strftime("%Y-%m-%d")
            details["cancel_at_period_end"] = sub.get("cancel_at_period_end", False)
            details["status"] = sub.get("status", "unknown")
        except Exception as e:
            log.warning(f"Could not fetch Stripe subscription: {e}")

    return details
