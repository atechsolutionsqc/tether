"""
routers/password_reset.py

Password reset flow:
  POST /api/auth/forgot-password  → generate token, send email
  GET  /api/auth/reset-password/{token} → validate token (public)
  POST /api/auth/reset-password   → consume token, set new password

Tokens:
  - 64-char hex string stored hashed in DB
  - Valid for 1 hour
  - Single-use (deleted on consumption)
  - Rate-limited: 3 requests per email per hour
"""
import os
import secrets
import hashlib
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from db.database import Base, get_db
from models.models import User
from security import hash_password

router = APIRouter()

APP_URL = os.environ.get("APP_URL", "https://usetether.ca")


# ── Model ──────────────────────────────────────────────────────────────────────

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


# ── Rate limit store (in-memory, per process) ─────────────────────────────────
# { email: [timestamp, timestamp, ...] }
_reset_attempts: dict = {}

def _check_rate_limit(email: str) -> None:
    """Allow max 3 reset requests per email per hour."""
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=1)
    attempts = [t for t in _reset_attempts.get(email, []) if t > cutoff]
    if len(attempts) >= 3:
        raise HTTPException(429, "Too many password reset requests. Please wait an hour.")
    attempts.append(now)
    _reset_attempts[email] = attempts


# ── Schemas ───────────────────────────────────────────────────────────────────

class ForgotRequest(BaseModel):
    email: EmailStr

class ResetRequest(BaseModel):
    token:        str
    new_password: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

def _generate_token(user_id: int, db: Session) -> str:
    # Invalidate any existing unused tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.used == False,  # noqa: E712
    ).delete()

    raw   = secrets.token_hex(32)
    token = PasswordResetToken(
        user_id    = user_id,
        token_hash = _hash_token(raw),
        expires_at = datetime.utcnow() + timedelta(hours=1),
    )
    db.add(token)
    db.commit()
    return raw


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(body: ForgotRequest, db: Session = Depends(get_db)):
    """
    Request a password reset email. Always returns 200 to avoid
    user enumeration — don't tell the caller if the email exists.
    """
    _check_rate_limit(body.email.lower())

    user = db.query(User).filter(
        User.email == body.email.lower()
    ).first()

    if user and user.active:
        raw_token = _generate_token(user.id, db)
        reset_url = f"{APP_URL}/reset-password/{raw_token}"

        # Send email (import here to avoid circular at module level)
        from email_service import send_password_reset
        sent = send_password_reset(user.email, user.name or "there", reset_url)
        if not sent:
            # Log but don't fail — token is still valid
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to send reset email to {user.email}. "
                f"Reset URL: {reset_url}"
            )

    # Always return the same response
    return {
        "message": "If that email is registered, a reset link has been sent."
    }


@router.get("/reset-password/{token}")
def validate_reset_token(token: str, db: Session = Depends(get_db)):
    """Validate a reset token without consuming it (used by the frontend to show the form)."""
    record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == _hash_token(token),
        PasswordResetToken.used == False,  # noqa: E712
    ).first()

    if not record or record.expires_at < datetime.utcnow():
        raise HTTPException(400, "This reset link is invalid or has expired.")

    return {
        "valid": True,
        "email": record.user.email,
        "name":  record.user.name,
    }


@router.post("/reset-password")
def reset_password(body: ResetRequest, db: Session = Depends(get_db)):
    """Consume a token and set a new password."""
    if len(body.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")

    record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == _hash_token(body.token),
        PasswordResetToken.used == False,  # noqa: E712
    ).first()

    if not record or record.expires_at < datetime.utcnow():
        raise HTTPException(400, "This reset link is invalid or has expired.")

    # Update password
    record.user.password_hash = hash_password(body.new_password)
    record.used = True
    db.commit()

    return {"message": "Password updated. You can now log in."}
