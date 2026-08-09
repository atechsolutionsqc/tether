"""
routers/totp.py — TOTP (authenticator app) 2FA for MSP admin accounts.

Flow:
  1. POST /api/auth/totp/setup       → returns {secret, otpauth_uri, qr_svg}
  2. POST /api/auth/totp/verify      → confirm first code → enables 2FA
  3. DELETE /api/auth/totp           → disable 2FA (requires current password)

  Login flow when 2FA is active:
  4. POST /api/auth/login            → returns {totp_required:true, totp_token:"..."}
  5. POST /api/auth/totp/authenticate → {totp_token, code} → returns full JWT
"""
import io
import os
import pyotp
import qrcode
import qrcode.image.svg

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from models.models import User, UserTotp
from security import (get_current_user, CurrentUser, verify_password,
                       create_token, decode_totp_challenge_token)
from rate_limit import is_limited, consume
import audit

router = APIRouter()

APP_NAME = os.environ.get("TOTP_APP_NAME", "Tether")


# ── Schemas ───────────────────────────────────────────────────────────────────

class TotpVerifyIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)

class TotpDisableIn(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)

class TotpAuthenticateIn(BaseModel):
    totp_token: str
    code: str = Field(..., min_length=6, max_length=8)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_totp_rate(ip: str) -> None:
    if is_limited("totp_fail", ip, limit=10):
        raise HTTPException(429, "Too many TOTP attempts. Please wait 5 minutes.")

def _record_totp_fail(ip: str) -> None:
    consume("totp_fail", ip, limit=10, window_sec=5 * 60)

def _svg_qr(uri: str) -> str:
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(uri, image_factory=factory, box_size=8)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


# ── Setup ─────────────────────────────────────────────────────────────────────

@router.post("/setup")
def totp_setup(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
):
    """Generate a new TOTP secret for the current user. Does not enable 2FA until /verify is called."""
    if not cu.is_msp_staff:
        raise HTTPException(403, "2FA is only available for MSP accounts")

    secret = pyotp.random_base32()
    user = db.query(User).get(cu.id)
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=APP_NAME)

    # Store or replace pending secret (enabled=False until verified)
    existing = db.query(UserTotp).filter(UserTotp.user_id == cu.id).first()
    if existing:
        existing.secret  = secret
        existing.enabled = False
    else:
        db.add(UserTotp(user_id=cu.id, secret=secret, enabled=False))
    db.commit()

    return {
        "secret":      secret,
        "otpauth_uri": uri,
        "qr_svg":      _svg_qr(uri),
    }


# ── Verify (confirm + enable) ─────────────────────────────────────────────────

@router.post("/verify")
def totp_verify(
    body: TotpVerifyIn,
    request: Request,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
):
    """Confirm the first TOTP code to activate 2FA."""
    ip = request.client.host if request.client else "unknown"
    _check_totp_rate(ip)

    if not cu.is_msp_staff:
        raise HTTPException(403, "2FA is only available for MSP accounts")

    record = db.query(UserTotp).filter(UserTotp.user_id == cu.id).first()
    if not record:
        raise HTTPException(400, "Call /setup first to generate a secret")

    totp = pyotp.TOTP(record.secret)
    if not totp.verify(body.code, valid_window=1):
        _record_totp_fail(ip)
        raise HTTPException(400, "Invalid code")

    record.enabled = True
    db.commit()

    user = db.query(User).get(cu.id)
    audit.log(db, "auth.totp_enabled", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=cu.tenant_id,
              resource_id=user.email, ip_address=ip)
    return {"ok": True, "message": "2FA is now active"}


# ── Disable ───────────────────────────────────────────────────────────────────

@router.delete("")
def totp_disable(
    body: TotpDisableIn,
    request: Request,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
):
    """Disable 2FA. Requires current password to prevent account takeover via stolen session."""
    ip = request.client.host if request.client else "unknown"
    _check_totp_rate(ip)

    if not cu.is_msp_staff:
        raise HTTPException(403, "2FA is only available for MSP accounts")

    user = db.query(User).get(cu.id)
    if not verify_password(body.password, user.password_hash):
        _record_totp_fail(ip)
        raise HTTPException(400, "Incorrect password")

    record = db.query(UserTotp).filter(UserTotp.user_id == cu.id).first()
    if record:
        db.delete(record)
        db.commit()

    audit.log(db, "auth.totp_disabled", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=cu.tenant_id,
              resource_id=user.email, ip_address=ip)
    return {"ok": True, "message": "2FA has been disabled"}


# ── Authenticate (exchange challenge token + code for full JWT) ───────────────

@router.post("/authenticate")
def totp_authenticate(
    body: TotpAuthenticateIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Second factor: exchange a TOTP challenge token + authenticator code for a full session JWT."""
    ip = request.client.host if request.client else "unknown"
    _check_totp_rate(ip)

    user_id = decode_totp_challenge_token(body.totp_token)

    user = db.query(User).get(user_id)
    if not user or not user.active:
        raise HTTPException(401, "User not found or inactive")

    record = db.query(UserTotp).filter(
        UserTotp.user_id == user_id, UserTotp.enabled == True  # noqa: E712
    ).first()
    if not record:
        raise HTTPException(400, "TOTP not configured for this account")

    totp = pyotp.TOTP(record.secret)
    if not totp.verify(body.code, valid_window=1):
        _record_totp_fail(ip)
        audit.log(db, "auth.totp_failed", resource_id=user.email, ip_address=ip)
        raise HTTPException(400, "Invalid code")

    user.last_login = __import__("datetime").datetime.utcnow()
    db.commit()

    audit.log(db, "auth.login", actor_id=user.id, actor_email=user.email,
              actor_name=user.name, tenant_id=user.tenant_id,
              resource_id=user.email, ip_address=ip)
    return {"access_token": create_token(user.id, user.tenant_id, user.is_msp_staff,
                                         user.password_hash), "token_type": "bearer"}


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
def totp_status(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
):
    """Returns whether 2FA is currently enabled for the authenticated user."""
    record = db.query(UserTotp).filter(
        UserTotp.user_id == cu.id, UserTotp.enabled == True  # noqa: E712
    ).first()
    return {"enabled": bool(record)}
