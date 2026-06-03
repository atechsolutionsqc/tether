"""
routers/demo.py

Called by the Cloudflare Worker every hour to wipe and reseed the demo database.
Protected by X-Reset-Secret header — only the Worker knows the secret.

Mount in main.py only when DEPLOYMENT_MODE=demo:
  if os.environ.get("DEPLOYMENT_MODE") == "demo":
      from routers import demo as demo_router
      app.include_router(demo_router.router, prefix="/api/admin", tags=["demo"])
"""
import os
from datetime import date, timedelta
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session

from db.database import SessionLocal
from models.models import (
    Asset, Category, Location, Employee, CheckoutLog,
    AssetRequest, InviteToken, User, Tenant, MspBilling,
)
from security import hash_password

router  = APIRouter()
SECRET  = os.environ.get("RESET_SECRET", "")


def _verify(request: Request):
    if SECRET and request.headers.get("X-Reset-Secret") != SECRET:
        raise HTTPException(403, "Forbidden")


@router.get("/demo/stats")
def demo_stats():
    """Public endpoint — live asset count for the demo page counter."""
    db = SessionLocal()
    try:
        return {
            "total_assets": db.query(Asset).count(),
            "total_clients": db.query(Tenant).count() - 1,   # exclude MSP root
            "open_requests": db.query(AssetRequest).filter(AssetRequest.status == "open").count(),
        }
    finally:
        db.close()


@router.post("/demo-reset")
async def demo_reset(request: Request):
    """Called by Cloudflare Worker cron every hour."""
    _verify(request)
    db = SessionLocal()
    try:
        _wipe(db)
        _seed(db)
        return {"ok": True, "message": "Demo reset complete"}
    finally:
        db.close()


def _wipe(db: Session):
    db.query(CheckoutLog).delete()
    db.query(AssetRequest).delete()
    db.query(InviteToken).delete()
    db.query(Asset).delete()
    db.query(Employee).delete()
    db.query(Location).delete()
    db.query(Category).delete()
    db.query(User).filter(User.is_msp_staff == False).delete()   # noqa: E712
    db.query(Tenant).delete()
    db.commit()


def _seed(db: Session):
    from models.models import Role

    msp_admin_role    = db.query(Role).filter(Role.name == "msp_admin").first()
    client_admin_role = db.query(Role).filter(Role.name == "client_admin").first()
    client_mgr_role   = db.query(Role).filter(Role.name == "client_manager").first()
    client_view_role  = db.query(Role).filter(Role.name == "client_viewer").first()

    # ── MSP admin user (keep existing or recreate) ────────────────
    msp_user = db.query(User).filter(User.is_msp_staff == True).first()   # noqa: E712
    if not msp_user:
        msp_user = User(
            name="Demo MSP Admin", email="demo-msp@usetether.ca",
            password_hash=hash_password("demo1234"),
            role_id=msp_admin_role.id, is_msp_staff=True, tenant_id=None,
        )
        db.add(msp_user)
        db.flush()

    # ── Tenants ───────────────────────────────────────────────────
    tenants_data = [
        ("Acme Corp",    "acme",   "#d4f034", "USD"),
        ("Nexus Tech",   "nexus",  "#3b82f6", "USD"),
        ("Spark Media",  "spark",  "#f59e0b", "GBP"),
        ("Blue Oak Law", "blueoak","#10b981", "CAD"),
    ]
    tenants = {}
    for name, slug, accent, currency in tenants_data:
        t = Tenant(name=name, slug=slug, accent_color=accent, currency=currency)
        db.add(t); db.flush()
        tenants[slug] = t

    # ── Per-tenant seed ───────────────────────────────────────────
    cat_data = [
        ("Laptop", "laptop"), ("Desktop", "monitor"), ("Monitor", "tv"),
        ("Phone", "smartphone"), ("Server", "server"),
        ("Network", "wifi"), ("Peripheral", "mouse"),
    ]
    loc_data = ["Head Office", "Warehouse", "Remote"]

    for slug, tenant in tenants.items():
        cats = {}
        for cname, icon in cat_data:
            c = Category(tenant_id=tenant.id, name=cname, icon=icon)
            db.add(c); db.flush()
            cats[cname] = c

        locs = {}
        for lname in loc_data:
            l = Location(tenant_id=tenant.id, name=lname)
            db.add(l); db.flush()
            locs[lname] = l

        # People
        emp_data = [
            ("Sarah Chen", "sarah@" + slug + ".com", "Engineering"),
            ("Marcus Webb", "marcus@" + slug + ".com", "Sales"),
            ("Priya Patel", "priya@" + slug + ".com", "Design"),
        ]
        emps = {}
        for ename, email, dept in emp_data:
            e = Employee(tenant_id=tenant.id, name=ename, email=email, department=dept)
            db.add(e); db.flush()
            emps[ename] = e

        # Client demo user
        client_user = User(
            name="Demo Client User",
            email="demo-client@" + slug + ".demo",
            password_hash=hash_password("demo1234"),
            role_id=client_admin_role.id,
            is_msp_staff=False,
            tenant_id=tenant.id,
        )
        db.add(client_user)

        # Assets
        prefix = slug[:2].upper()
        assets_data = [
            (f"{prefix}-001", "MacBook Pro 16",   "Apple",     "M3 Max",     cats["Laptop"],   locs["Head Office"], "deployed",     emps["Sarah Chen"],  3499, "2027-03-01"),
            (f"{prefix}-002", "Dell Latitude 7440","Dell",      "7440",       cats["Laptop"],   locs["Remote"],      "deployed",     emps["Marcus Webb"], 1450, "2027-06-12"),
            (f"{prefix}-003", "ThinkPad X1 Carbon","Lenovo",    "X1",         cats["Laptop"],   locs["Head Office"], "available",    None,                1799, "2026-06-10"),
            (f"{prefix}-004", "Dell UltraSharp 27","Dell",      "U2724DE",    cats["Monitor"],  locs["Head Office"], "deployed",     emps["Priya Patel"], 620,  "2027-01-20"),
            (f"{prefix}-005", "iPhone 15 Pro",     "Apple",     "A2848",      cats["Phone"],    locs["Remote"],      "deployed",     emps["Sarah Chen"],  1099, "2026-02-15"),
            (f"{prefix}-006", "PowerEdge R760",    "Dell",      "R760",       cats["Server"],   locs["Warehouse"],   "available",    None,                8200, "2028-09-01"),
            (f"{prefix}-007", "Cisco Catalyst",    "Cisco",     "9300",       cats["Network"],  locs["Warehouse"],   "maintenance",  None,                4100, "2025-06-01"),
            (f"{prefix}-008", "Logitech MX Master","Logitech",  "3S",         cats["Peripheral"],locs["Head Office"],"available",   None,                99,   "2026-04-01"),
            (f"{prefix}-009", "iMac 24",           "Apple",     "M3",         cats["Desktop"],  locs["Head Office"], "retired",      None,                1599, "2024-08-01"),
            (f"{prefix}-010", "LG UltraWide",      "LG",        "40WP95C",    cats["Monitor"],  locs["Remote"],      "available",    None,                1299, "2027-07-01"),
        ]
        for tag, name, mfr, model, cat, loc, status, emp, cost, warranty in assets_data:
            a = Asset(
                tenant_id=tenant.id, asset_tag=tag, name=name,
                manufacturer=mfr, model=model, status=status,
                category_id=cat.id, location_id=loc.id,
                assigned_to_id=emp.id if emp else None,
                purchase_cost=cost,
                warranty_expiry=date.fromisoformat(warranty),
                purchase_date=date(2024, 1, 15),
            )
            db.add(a); db.flush()

            # Checkout log for deployed assets
            if emp:
                db.add(CheckoutLog(
                    asset_id=a.id, employee_id=emp.id,
                    employee_name=emp.name, action="checkout",
                    note="Assigned at onboarding",
                ))

        # Open requests
        for title, priority in [
            ("Need 2 monitors for new dev hires", "high"),
            ("Replace aging ThinkPad X1",         "normal"),
        ]:
            db.add(AssetRequest(
                tenant_id=tenant.id, requested_by_name="Sarah Chen",
                title=title, priority=priority, status="open",
                description="Please action when possible.",
            ))

    db.commit()
