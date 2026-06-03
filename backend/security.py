import os
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from db.database import get_db

SECRET_KEY         = os.environ.get("SECRET_KEY", "change-me-in-production-please-set-a-real-secret")
ALGORITHM          = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7
BASE_DOMAIN        = os.environ.get("BASE_DOMAIN", "localhost")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_token(user_id: int, tenant_id: Optional[int], is_msp_staff: bool) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({
        "sub": str(user_id),
        "tid": tenant_id,          # None for MSP staff
        "msp": is_msp_staff,
        "exp": expire,
    }, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Could not validate credentials",
                            headers={"WWW-Authenticate": "Bearer"})


# ── Tenant resolution from request host ──────────────────────────────────────

def resolve_tenant_slug(request: Request) -> Optional[str]:
    """
    Extract tenant slug from subdomain.
    acme.usetether.ca  → "acme"
    acme.localhost      → "acme"
    localhost           → None  (MSP root)
    """
    host = request.headers.get("host", "").split(":")[0]  # strip port
    base = BASE_DOMAIN.split(":")[0]

    if host == base or host in ("localhost", "127.0.0.1", "testclient"):
        return None
    if host.endswith("." + base):
        return host[: -(len(base) + 1)]
    # Could be a custom domain — caller handles lookup
    return host  # return raw host; router will do DB lookup


# ── Current-user dependency ───────────────────────────────────────────────────

class CurrentUser:
    """Attached to request state after auth."""
    def __init__(self, user):
        self.id          = user.id
        self.email       = user.email
        self.name        = user.name
        self.tenant_id   = user.tenant_id
        self.is_msp_staff = user.is_msp_staff
        self.role_name   = user.role.name if user.role else ""
        # build effective permission set: role defaults + overrides
        granted = {rp.permission.key for rp in user.role.permissions} if user.role else set()
        for ov in user.permission_overrides:
            if ov.granted:
                granted.add(ov.permission.key)
            else:
                granted.discard(ov.permission.key)
        self._perms = granted

    def can(self, perm: str) -> bool:
        return perm in self._perms

    def require(self, perm: str):
        if not self.can(perm):
            raise HTTPException(status_code=403, detail=f"Permission required: {perm}")


def get_current_user(token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> CurrentUser:
    from models.models import User
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).get(int(user_id))
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return CurrentUser(user)


def get_tenant_id(request: Request, db: Session = Depends(get_db),
                  current_user: CurrentUser = Depends(get_current_user)) -> Optional[int]:
    """
    Determine which tenant_id to scope queries to.
    - MSP staff hitting root domain → tenant_id from query param or None (all tenants)
    - MSP staff hitting a subdomain → scoped to that tenant
    - Client user → always their own tenant
    """
    from models.models import Tenant, TenantDomain

    slug = resolve_tenant_slug(request)

    if current_user.is_msp_staff:
        if slug is None:
            # MSP root — they may pass ?tenant=<slug> to scope
            t_slug = request.query_params.get("tenant")
            if t_slug:
                t = db.query(Tenant).filter(Tenant.slug == t_slug).first()
                return t.id if t else None
            return None  # no scoping, sees everything
        else:
            # resolve slug or custom domain
            t = (db.query(Tenant).filter(Tenant.slug == slug).first() or
                 db.query(TenantDomain).filter(TenantDomain.domain == slug,
                                               TenantDomain.verified == True).first())
            return t.tenant_id if hasattr(t, "tenant_id") else (t.id if t else None)
    else:
        # client user always scoped to their own tenant
        return current_user.tenant_id
