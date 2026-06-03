import os, sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Start background scheduler
    from scheduler import start_scheduler
    from backup_service import BACKUP_ENABLED, backup_loop
    _scheduler_tasks = await start_scheduler()
    if BACKUP_ENABLED:
        import asyncio
        _scheduler_tasks.append(asyncio.create_task(backup_loop()))
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


# ── Public: tenant branding (for white-label login page) ─────────────────────
@app.get("/api/public/branding")
def public_branding(request: Request, db: Session = Depends(get_db)):
    """Returns tenant branding for the login page — no auth required."""
    slug = resolve_tenant_slug(request)
    if not slug:
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
            "logo_url": t.logo_url, "accent_color": t.accent_color, "mode": "tenant"}


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
    db.commit()
    return {"ok": True}


# ── Demo mode (mounted only when DEPLOYMENT_MODE=demo) ───────────────────────
if os.environ.get("DEPLOYMENT_MODE") == "demo":
    from routers import demo as demo_router
    app.include_router(demo_router.router, prefix="/api/admin", tags=["demo"])

# ── Frontend SPA ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")
INDEX_HTML = os.path.join(FRONTEND_DIR, "templates", "index.html")


@app.get("/")
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str = ""):
    return FileResponse(INDEX_HTML)
