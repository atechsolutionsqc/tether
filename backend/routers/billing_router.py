"""
/api/billing — MSP billing & usage endpoints.
All endpoints require MSP staff. In self-hosted mode they still work
but return saas=false so the UI knows not to show upgrade prompts.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

import audit
from db.database import get_db
from models.models import Asset, MspBilling
from security import get_current_user, CurrentUser
from billing import is_saas, TIERS, TIER_ORDER, get_tier, usage_status, next_tier

router = APIRouter()


def _billing_row(db: Session) -> MspBilling:
    row = db.query(MspBilling).first()
    if not row:
        row = MspBilling(tier="selfhosted" if not is_saas() else "trial")
        db.add(row); db.commit(); db.refresh(row)
    return row


@router.get("/status")
def billing_status(db: Session = Depends(get_db),
                   cu: CurrentUser = Depends(get_current_user)):
    cu.require("msp.dashboard")
    row   = _billing_row(db)
    total = db.query(Asset).count()
    us    = usage_status(total, row.tier)
    tier  = get_tier(row.tier)
    nxt   = next_tier(row.tier)

    # Check trial expiry
    trial_expired = False
    trial_days_left = None
    if row.tier == "trial" and row.trial_ends_at:
        delta = row.trial_ends_at - datetime.utcnow()
        trial_days_left = max(0, delta.days)
        trial_expired   = delta.total_seconds() <= 0

    return {
        "saas":             is_saas(),
        "tier":             row.tier,
        "tier_name":        tier["name"],
        "tier_price_cad":   tier["price_cad"],
        "asset_limit":      tier["asset_limit"],
        "total_assets":     total,
        "usage_pct":        us["pct"],
        "usage_status":     us["status"],   # ok / warning / exceeded
        "trial_days_left":  trial_days_left,
        "trial_expired":    trial_expired,
        "next_tier":        nxt,
        "billing_email":    row.billing_email,
    }


@router.get("/tiers")
def list_tiers(cu: CurrentUser = Depends(get_current_user)):
    cu.require("msp.dashboard")
    return [
        {"key": k, **TIERS[k]}
        for k in TIER_ORDER
        if k != "selfhosted"
    ]


class TierUpdate(BaseModel):
    tier: str
    billing_email: str = ""
    notes: str = ""


@router.put("/tier")
def update_tier(body: TierUpdate, request: Request,
                db: Session = Depends(get_db),
                cu: CurrentUser = Depends(get_current_user)):
    """MSP admin manually sets the active tier (used by you to provision accounts)."""
    cu.require("tenants.manage")
    if body.tier not in TIERS:
        raise HTTPException(400, f"Unknown tier. Valid: {list(TIERS.keys())}")
    row = _billing_row(db)
    old_tier = row.tier
    row.tier           = body.tier
    row.billing_email  = body.billing_email or row.billing_email
    row.notes          = body.notes or row.notes
    # Clear trial expiry if upgrading to a real tier
    if body.tier not in ("trial",):
        row.trial_ends_at = None
    db.commit()
    audit.log(db, "billing.tier_change", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, resource="billing",
              detail=f"Tier changed from {old_tier} to {body.tier}",
              ip_address=request.client.host if request.client else "")
    return {"ok": True, "tier": row.tier}
