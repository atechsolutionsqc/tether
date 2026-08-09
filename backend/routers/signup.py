"""
routers/signup.py

Public self-serve MSP signup. Creates:
  - MSP admin user account
  - Default demo tenant
  - MspBilling row (30-day trial)
  - Sends welcome email

POST /api/auth/signup

Rate limited: 5 signups per IP per hour.

In selfhosted mode, signup is disabled by default — the admin account
is created at first boot via env vars. Set ALLOW_SIGNUP=true to enable
self-registration on self-hosted installs.
"""
import os
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session
from slugify import slugify

from db.database import get_db
from models.models import User, Tenant, Category, Location, Role, MspBilling
from security import hash_password, validate_password_strength, create_token
from billing import is_saas
from rate_limit import consume

log = logging.getLogger(__name__)
router = APIRouter()
APP_URL = os.environ.get("APP_URL", "https://usetether.ca")

# Only allow signup in SaaS mode, or if explicitly enabled on self-hosted
SIGNUP_ENABLED = is_saas() or os.environ.get("ALLOW_SIGNUP", "false").lower() == "true"

def _check_signup_rate(ip: str) -> None:
    allowed = consume("signup", ip, limit=5, window_sec=60 * 60)
    if not allowed:
        raise HTTPException(429, "Too many signup attempts from this IP. Please wait an hour.")


# ── Schema ────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name:         str
    email:        EmailStr
    password:     str
    msp_name:     str          # The MSP's company name
    agree_terms:  bool = False

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        try:
            validate_password_strength(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("msp_name")
    @classmethod
    def msp_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("MSP / company name is required")
        return v

    @field_validator("agree_terms")
    @classmethod
    def must_agree(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must agree to the terms of service")
        return v


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/signup")
def signup(body: SignupRequest, request: Request, db: Session = Depends(get_db)):
    if not SIGNUP_ENABLED:
        raise HTTPException(
            403,
            "Self-serve signup is disabled on this installation. "
            "Contact the administrator to create an account."
        )

    ip = request.client.host if request.client else "unknown"
    _check_signup_rate(ip)

    # Check email not already taken
    existing = db.query(User).filter(User.email == body.email.lower()).first()
    if existing:
        raise HTTPException(400, "An account with that email already exists.")

    # Get MSP admin role
    msp_admin_role = db.query(Role).filter(Role.name == "msp_admin").first()
    if not msp_admin_role:
        raise HTTPException(500, "Roles not seeded — run database initialisation first.")

    # Create the MSP admin user
    user = User(
        name          = body.name.strip(),
        email         = body.email.lower(),
        password_hash = hash_password(body.password),
        role_id       = msp_admin_role.id,
        is_msp_staff  = True,
        tenant_id     = None,
        active        = True,
    )
    db.add(user)
    db.flush()

    # Create a default demo tenant so the MSP has something to explore
    slug = _unique_slug(body.msp_name, db)
    tenant = Tenant(
        name         = body.msp_name.strip(),
        slug         = slug,
        accent_color = "#d4f034",
        currency     = "CAD",
    )
    db.add(tenant)
    db.flush()
    _seed_tenant_defaults(tenant.id, db)

    # Create / update billing row
    billing = db.query(MspBilling).first()
    if billing:
        # Existing install — just update email and name
        billing.billing_email = body.email.lower()
        billing.msp_name      = body.msp_name.strip()
    else:
        billing = MspBilling(
            tier          = "trial",
            trial_ends_at = datetime.utcnow() + timedelta(days=30),
            billing_email = body.email.lower(),
            msp_name      = body.msp_name.strip(),
        )
        db.add(billing)

    db.commit()
    db.refresh(user)

    # Send welcome email
    try:
        from email_service import send_welcome
        send_welcome(user.email, user.name, APP_URL, "MSP Admin")
    except Exception as e:
        log.warning(f"Welcome email failed for {user.email}: {e}")

    # Return a login token immediately — no separate login step needed
    token = create_token(user.id, None, True, user.password_hash)
    log.info(f"New MSP signup: {user.email} ({body.msp_name})")

    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {
            "id":           user.id,
            "name":         user.name,
            "email":        user.email,
            "is_msp_staff": True,
        },
        "trial_days": 30,
        "message": f"Welcome to Tether! Your 30-day trial has started.",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique_slug(name: str, db: Session) -> str:
    """Generate a unique tenant slug from the MSP name."""
    base = slugify(name, max_length=30) or "msp"
    slug = base
    n    = 2
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        slug = f"{base}-{n}"
        n   += 1
    return slug


def _seed_tenant_defaults(tenant_id: int, db: Session) -> None:
    """Seed default categories and locations for a new tenant."""
    categories = [
        ("Laptop",     "laptop"),
        ("Desktop",    "desktop"),
        ("Monitor",    "monitor"),
        ("Phone",      "smartphone"),
        ("Server",     "server"),
        ("Network",    "wifi"),
        ("Peripheral", "mouse"),
    ]
    locations = ["Head Office", "Warehouse", "Remote"]

    for name, icon in categories:
        db.add(Category(tenant_id=tenant_id, name=name, icon=icon))

    for lname in locations:
        db.add(Location(tenant_id=tenant_id, name=lname))
