"""
billing.py — Tier definitions, usage checks, and deployment-mode gate.

DEPLOYMENT_MODE=selfhosted (default) → no limits enforced, no billing UI shown.
DEPLOYMENT_MODE=saas                 → tiers enforced, billing UI shown.
"""
import os
from typing import Optional

DEPLOYMENT_MODE = os.environ.get("DEPLOYMENT_MODE", "selfhosted").lower()

def is_saas() -> bool:
    return DEPLOYMENT_MODE == "saas"


# ── Tier catalogue ─────────────────────────────────────────────────────────────

TIERS = {
    "starter": {
        "name":       "Starter",
        "asset_limit": 250,
        "price_cad":  49,
        "description":"Up to 250 managed assets, unlimited clients & users.",
    },
    "growth": {
        "name":       "Growth",
        "asset_limit": 1_000,
        "price_cad":  129,
        "description":"Up to 1,000 managed assets, unlimited clients & users.",
    },
    "scale": {
        "name":       "Scale",
        "asset_limit": 5_000,
        "price_cad":  349,
        "description":"Up to 5,000 managed assets, unlimited clients & users.",
    },
    "enterprise": {
        "name":       "Enterprise",
        "asset_limit": None,      # unlimited
        "price_cad":  None,       # custom
        "description":"Unlimited assets. Custom pricing.",
    },
    "selfhosted": {
        "name":       "Self-hosted",
        "asset_limit": None,
        "price_cad":  0,
        "description":"No limits. You manage the infrastructure.",
    },
    "trial": {
        "name":       "Free Trial",
        "asset_limit": 250,
        "price_cad":  0,
        "description":"30-day free trial. No card required.",
    },
}

TIER_ORDER = ["trial", "starter", "growth", "scale", "enterprise"]

# Asset threshold at which we show a usage warning (% of limit)
WARN_THRESHOLD = 0.80


def get_tier(tier_key: str) -> dict:
    return TIERS.get(tier_key, TIERS["starter"])


def asset_limit(tier_key: str) -> Optional[int]:
    return get_tier(tier_key).get("asset_limit")


def usage_status(current: int, tier_key: str) -> dict:
    """
    Returns usage info for a given asset count + tier.
    status: "ok" | "warning" | "exceeded"
    """
    if not is_saas():
        return {"status": "ok", "current": current, "limit": None,
                "pct": 0, "saas": False}

    limit = asset_limit(tier_key)
    if limit is None:
        return {"status": "ok", "current": current, "limit": None,
                "pct": 0, "saas": True}

    pct = current / limit
    if pct >= 1.0:
        status = "exceeded"
    elif pct >= WARN_THRESHOLD:
        status = "warning"
    else:
        status = "ok"

    return {
        "status":  status,
        "current": current,
        "limit":   limit,
        "pct":     round(pct * 100, 1),
        "saas":    True,
    }


def next_tier(tier_key: str) -> Optional[dict]:
    """Return the next tier up, or None if already at top."""
    try:
        idx = TIER_ORDER.index(tier_key)
        if idx < len(TIER_ORDER) - 1:
            key = TIER_ORDER[idx + 1]
            return {"key": key, **TIERS[key]}
    except ValueError:
        pass
    return None
