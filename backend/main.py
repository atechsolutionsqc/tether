import logging
import logging.config
import json
import os, sys, time
from contextlib import asynccontextmanager
from typing import Optional

_LOG_FORMAT = os.environ.get("LOG_FORMAT", "text")

if _LOG_FORMAT == "json":
    class _JsonFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({
                "ts":      self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level":   record.levelname,
                "logger":  record.name,
                "msg":     record.getMessage(),
                **({"exc": self.formatException(record.exc_info)} if record.exc_info else {}),
            })
    _handler = logging.StreamHandler()
    _handler.setFormatter(_JsonFormatter())
    logging.root.setLevel(logging.INFO)
    logging.root.handlers = [_handler]
else:
    logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import init_db, get_db
from models.models import Tenant, TenantDomain
from schemas.schemas import SettingsIn
from security import get_current_user, CurrentUser, get_tenant_id, resolve_tenant_slug
from routers import assets, categories, locations, users, dashboard, auth
from routers import tenants as tenants_router
from routers import user_mgmt, invites, requests as requests_router
from routers import billing_router
from routers import password_reset as pw_reset_router
from routers import stripe_router, signup as signup_router
from routers import admin_router
from routers import reports as reports_router
from routers import licences as licences_router
from routers import custom_fields as custom_fields_router
from routers import totp as totp_router
from routers import saved_filters as saved_filters_router


_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception:
        _log.exception("init_db() failed — check database connection and schema")
        raise
    # Start background scheduler (includes backup loop when BACKUP_ENABLED=true)
    from scheduler import start_scheduler
    _scheduler_tasks = await start_scheduler()
    yield
    # Cancel background tasks on shutdown
    for task in _scheduler_tasks:
        task.cancel()


app = FastAPI(title="Tether", version="3.0.0", lifespan=lifespan)

# ── Security headers ──────────────────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        csp = "; ".join([
            "default-src 'self'",
            "script-src 'self'",
            # Inline styles are used in generated UI markup.
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com data:",
            "img-src 'self' data: blob: https:",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "frame-ancestors 'none'",
            "form-action 'self'",
        ])
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

_access_log = logging.getLogger("tether.access")

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        if _LOG_FORMAT == "json":
            _access_log.info(json.dumps({
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "host": request.headers.get("host", ""),
            }))
        else:
            _access_log.debug("%s %s %s %.1fms",
                request.method, request.url.path, response.status_code, duration_ms)
        return response

app.add_middleware(RequestLoggingMiddleware)

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

# ── API routers ───────────────────────────────────────────────────────────────
app.include_router(auth.router,             prefix="/api/auth",       tags=["auth"])
app.include_router(dashboard.router,        prefix="/api/dashboard",  tags=["dashboard"])
app.include_router(assets.router,           prefix="/api/assets",     tags=["assets"])
app.include_router(categories.router,       prefix="/api/categories", tags=["categories"])
app.include_router(locations.router,        prefix="/api/locations",  tags=["locations"])
app.include_router(users.router,            prefix="/api/employees",  tags=["employees"])
app.include_router(tenants_router.router,   prefix="/api/tenants",    tags=["tenants"])
app.include_router(user_mgmt.router,        prefix="/api/users",      tags=["users"])
app.include_router(invites.router,          prefix="/api/invites",    tags=["invites"])
app.include_router(requests_router.router,  prefix="/api/requests",   tags=["requests"])
app.include_router(billing_router.router,   prefix="/api/billing",    tags=["billing"])
app.include_router(pw_reset_router.router,  prefix="/api/auth",       tags=["auth"])
app.include_router(signup_router.router,    prefix="/api/auth",       tags=["auth"])
app.include_router(stripe_router.router,    prefix="/api/stripe",     tags=["stripe"])
app.include_router(admin_router.router,     prefix="/api/admin",      tags=["admin"])
app.include_router(reports_router.router,   prefix="/api/reports",    tags=["reports"])
app.include_router(licences_router.router,      prefix="/api/licences",      tags=["licences"])
app.include_router(custom_fields_router.router, prefix="/api/custom-fields", tags=["custom-fields"])
app.include_router(saved_filters_router.router, prefix="/api/saved-filters", tags=["saved-filters"])
app.include_router(totp_router.router,          prefix="/api/auth/totp",    tags=["auth"])


# ── Public: tenant branding (for white-label login page) ─────────────────────
@app.get("/api/public/branding")
def public_branding(request: Request, db: Session = Depends(get_db)):
    """Returns tenant branding for the login page — no auth required."""
    slug = resolve_tenant_slug(request)
    if not slug:
        # In standalone mode the root domain IS the company — return their branding directly
        if os.environ.get("DEPLOYMENT_MODE") == "standalone":
            t = db.query(Tenant).first()
            if t:
                return {"name": t.name, "logo_url": t.logo_url or "",
                        "accent_color": t.accent_color, "is_tenant": True,
                        "slug": t.slug, "standalone": True}
        return {"name": "Tether", "logo_url": "", "accent_color": "#d4f034",
                "is_tenant": False}
    tenant = (db.query(Tenant).filter(Tenant.slug == slug).first() or
              db.query(TenantDomain).filter(TenantDomain.domain == slug,
                                            TenantDomain.verified == True).first())
    if not tenant:
        return {"name": "Tether", "logo_url": "", "accent_color": "#d4f034",
                "is_tenant": False}
    t = tenant if isinstance(tenant, Tenant) else tenant.tenant
    return {"name": t.name, "logo_url": t.logo_url,
            "accent_color": t.accent_color, "is_tenant": True, "slug": t.slug}


# ── Public: demo credentials (only in demo mode) ─────────────────────────────
@app.get("/api/public/demo")
def public_demo_info():
    """Returns demo login info for the login page. Returns {enabled:false} in non-demo mode."""
    if os.environ.get("DEPLOYMENT_MODE") != "demo":
        return {"enabled": False}
    from routers.demo import _demo_password
    return {
        "enabled": True,
        "client": {
            "email":    "demo-client@acme.demo",
            "password": _demo_password("DEMO_CLIENT_PASSWORD", "client"),
            "slug":     "acme",
        },
        "msp": {
            "email":    "demo-msp@usetether.ca",
            "password": _demo_password("DEMO_MSP_PASSWORD", "msp"),
        },
    }


# ── Tenant settings (scoped) ──────────────────────────────────────────────────
@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db),
                 cu: CurrentUser = Depends(get_current_user),
                 tenant_id: Optional[int] = Depends(get_tenant_id)):
    if tenant_id is None:
        return {"name": "Tether MSP", "currency": "USD",
                "logo_url": "", "accent_color": "#d4f034", "mode": "msp"}
    t = db.query(Tenant).get(tenant_id)
    if not t: raise HTTPException(404, "Tenant not found")
    return {"name": t.name, "currency": t.currency,
            "logo_url": t.logo_url, "accent_color": t.accent_color, "mode": "tenant",
            "email_from_name": t.email_from_name or "",
            "email_from_address": t.email_from_address or "",
            "email_logo_url": t.email_logo_url or "",
            "email_accent_color": t.email_accent_color or "",
            "asset_tag_prefix": t.asset_tag_prefix or "",
            "webhook_url": t.webhook_url or "",
            "webhook_secret": t.webhook_secret or ""}


@app.put("/api/settings")
def update_settings(body: SettingsIn, db: Session = Depends(get_db),
                    cu: CurrentUser = Depends(get_current_user),
                    tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("settings.manage")
    if tenant_id is None: raise HTTPException(400, "Specify a tenant")
    t = db.query(Tenant).get(tenant_id)
    if not t: raise HTTPException(404, "Tenant not found")
    t.name = body.name; t.currency = body.currency
    t.logo_url = body.logo_url; t.accent_color = body.accent_color
    t.email_from_name = body.email_from_name or None
    t.email_from_address = body.email_from_address or None
    t.email_logo_url = body.email_logo_url or None
    t.email_accent_color = body.email_accent_color or None
    t.asset_tag_prefix = (body.asset_tag_prefix or "").strip().upper() or None
    t.webhook_url = (body.webhook_url or "").strip() or None
    t.webhook_secret = (body.webhook_secret or "").strip() or None
    db.commit()
    return {"ok": True}


# ── Health check (no auth required) ─────────────────────────────────────────
@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        raise HTTPException(503, "Database unavailable")
    return {
        "status": "ok",
        "version": app.version,
        "database": db_status,
        "deployment_mode": os.environ.get("DEPLOYMENT_MODE", "selfhosted"),
    }


# ── Demo mode (mounted only when DEPLOYMENT_MODE=demo) ───────────────────────
if os.environ.get("DEPLOYMENT_MODE") == "demo":
    from routers import demo as demo_router
    app.include_router(demo_router.router, prefix="/api/admin", tags=["demo"])

# ── Uploaded asset photos ─────────────────────────────────────────────────────
_UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")
os.makedirs(_UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_UPLOADS_DIR), name="uploads")

# ── Frontend SPA ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")
INDEX_HTML = os.path.join(FRONTEND_DIR, "templates", "index.html")


@app.get("/")
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str = ""):
    return FileResponse(INDEX_HTML)
