from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from db.database import get_db
from models.models import User
from schemas.schemas import Token, PasswordChange
from security import (verify_password, create_token, hash_password,
                       get_current_user, CurrentUser, resolve_tenant_slug)

router = APIRouter()

# ── Login rate limiting ────────────────────────────────────────────────────────
# Max 10 failed attempts per IP per 5 minutes
_login_attempts: dict = {}

def _check_login_rate(ip: str) -> None:
    from datetime import timedelta
    now    = datetime.utcnow()
    cutoff = now - timedelta(minutes=5)
    hits   = [t for t in _login_attempts.get(ip, []) if t > cutoff]
    if len(hits) >= 10:
        raise HTTPException(429, "Too many login attempts. Please wait 5 minutes.")
    _login_attempts[ip] = hits  # only count failures (appended below)

def _record_failed_login(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(datetime.utcnow())


@router.post("/login", response_model=Token)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db)):
    from models.models import Tenant, TenantDomain

    ip = request.client.host if request.client else "unknown"
    _check_login_rate(ip)

    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        _record_failed_login(ip)
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

    user.last_login = datetime.utcnow()
    db.commit()
    return Token(access_token=create_token(user.id, user.tenant_id, user.is_msp_staff))


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
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
