from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from db.database import get_db
from models.models import User
from schemas.schemas import Token, PasswordChange
from security import (verify_password, create_token, hash_password,
                       get_current_user, CurrentUser, resolve_tenant_slug,
                       validate_password_strength, create_totp_challenge_token)
from rate_limit import is_limited, consume, clear
import audit

router = APIRouter()

def _check_login_rate(ip: str, email: str) -> None:
    # IP-level guard: broad limit; not cleared on success so shared-NAT logins
    # can't reset an attacker's window.
    if is_limited("login_fail_ip", ip, limit=20):
        raise HTTPException(429, "Too many login attempts. Please wait 5 minutes.")
    # Per-email guard: tighter limit; cleared on success so a legitimate user's
    # own earlier typos don't keep blocking them.
    if is_limited("login_fail", email, limit=10):
        raise HTTPException(429, "Too many login attempts. Please wait 5 minutes.")

def _record_failed_login(ip: str, email: str) -> None:
    consume("login_fail_ip", ip, limit=20, window_sec=5 * 60)
    consume("login_fail", email, limit=10, window_sec=5 * 60)


@router.post("/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db)):
    from models.models import Tenant, TenantDomain

    ip = request.client.host if request.client else "unknown"
    _check_login_rate(ip, form.username)

    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        _record_failed_login(ip, form.username)
        audit.log(db, "auth.login_failed", resource_id=form.username,
                  detail="Failed login attempt", ip_address=ip)
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    # If logging in from a tenant subdomain, enforce tenant match
    slug = resolve_tenant_slug(request)
    if slug and not user.is_msp_staff:
        tenant = (db.query(Tenant).filter(Tenant.slug == slug).first() or
                  db.query(TenantDomain).filter(
                      TenantDomain.domain == slug, TenantDomain.verified == True
                  ).first())
        tid = tenant.tenant_id if hasattr(tenant, "tenant_id") else (tenant.id if tenant else None)
        if tid and user.tenant_id != tid:
            raise HTTPException(status_code=403, detail="Not authorised for this tenant")

    # Check if TOTP is enabled for this user — if so, issue a challenge token instead of a full session
    from models.models import UserTotp
    totp_record = db.query(UserTotp).filter(
        UserTotp.user_id == user.id, UserTotp.enabled == True  # noqa: E712
    ).first()
    if totp_record:
        clear("login_fail", form.username)
        return {"totp_required": True, "totp_token": create_totp_challenge_token(user.id)}

    user.last_login = datetime.utcnow()
    db.commit()
    clear("login_fail", form.username)  # clear per-email counter only; IP counter is intentionally kept
    audit.log(db, "auth.login", actor_id=user.id, actor_email=user.email,
              actor_name=user.name, tenant_id=user.tenant_id,
              resource_id=user.email, ip_address=ip)
    return Token(access_token=create_token(user.id, user.tenant_id, user.is_msp_staff,
                                           user.password_hash))


@router.get("/me")
def me(current_user: CurrentUser = Depends(get_current_user),
       db: Session = Depends(get_db)):
    user = db.query(User).get(current_user.id)
    tenant_name = user.tenant.name if user.tenant else None
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": current_user.role_name,
        "tenant_id": user.tenant_id,
        "tenant_name": tenant_name,
        "is_msp_staff": user.is_msp_staff,
        "permissions": list(current_user._perms),
    }


@router.post("/change-password")
def change_password(body: PasswordChange,
                    current_user: CurrentUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    user = db.query(User).get(current_user.id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        validate_password_strength(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
