from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.database import get_db
from models.models import Asset, AssetMaintenance, Category, Location, Employee, CheckoutLog, Tenant
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()


def _tenant_stats(db, tenant_id):
    """Stats for a single tenant."""
    base = db.query(Asset).filter(Asset.tenant_id == tenant_id)
    total = base.count()
    by_status = dict(db.query(Asset.status, func.count(Asset.id))
                     .filter(Asset.tenant_id == tenant_id)
                     .group_by(Asset.status).all())
    cats = db.query(Category).filter(Category.tenant_id == tenant_id).all()
    by_category = [{"name": c.name, "count": len(c.assets)} for c in cats if c.assets]
    total_value = db.query(func.coalesce(func.sum(Asset.purchase_cost), 0))\
                    .filter(Asset.tenant_id == tenant_id).scalar() or 0
    soon = date.today() + timedelta(days=30)
    expiring = base.filter(Asset.warranty_expiry != None,
                           Asset.warranty_expiry <= soon,
                           Asset.warranty_expiry >= date.today())\
                   .order_by(Asset.warranty_expiry).all()
    recent = db.query(CheckoutLog)\
               .join(Asset).filter(Asset.tenant_id == tenant_id)\
               .order_by(CheckoutLog.timestamp.desc()).limit(8).all()
    overdue_maint = db.query(AssetMaintenance).filter(
        AssetMaintenance.tenant_id == tenant_id,
        AssetMaintenance.status.in_(["scheduled", "overdue"]),
        AssetMaintenance.due_date < date.today(),
    ).count()
    upcoming_maint = db.query(AssetMaintenance).filter(
        AssetMaintenance.tenant_id == tenant_id,
        AssetMaintenance.status == "scheduled",
        AssetMaintenance.due_date >= date.today(),
        AssetMaintenance.due_date <= soon,
    ).order_by(AssetMaintenance.due_date).limit(5).all()
    return {
        "total_assets": total,
        "available":    by_status.get("available", 0),
        "deployed":     by_status.get("deployed", 0),
        "maintenance":  by_status.get("maintenance", 0),
        "retired":      by_status.get("retired", 0),
        "total_value":  round(total_value, 2),
        "by_category":  by_category,
        "by_status": [
            {"name": "Available",    "count": by_status.get("available", 0)},
            {"name": "Deployed",     "count": by_status.get("deployed", 0)},
            {"name": "Maintenance",  "count": by_status.get("maintenance", 0)},
            {"name": "Retired",      "count": by_status.get("retired", 0)},
        ],
        "overdue_maintenance": overdue_maint,
        "upcoming_maintenance": [
            {"id": m.id, "title": m.title, "due_date": m.due_date.isoformat(),
             "asset_id": m.asset_id,
             "asset_tag": m.asset.asset_tag if m.asset else "",
             "maintenance_type": m.maintenance_type}
            for m in upcoming_maint
        ],
        "expiring_warranties": [
            {"asset_tag": a.asset_tag, "name": a.name, "warranty_expiry": str(a.warranty_expiry)}
            for a in expiring
        ],
        "recent_activity": [
            {"asset_tag": r.asset.asset_tag if r.asset else "?",
             "action": r.action, "employee_name": r.employee_name,
             "timestamp": str(r.timestamp)}
            for r in recent
        ],
    }


@router.get("/client/{tenant_id}")
def client_drilldown(
    tenant_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
):
    """Full stats for a single client tenant. MSP staff only."""
    from fastapi import HTTPException
    cu.require("msp.dashboard")
    t = db.query(Tenant).get(tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    result = _tenant_stats(db, tenant_id)
    result["mode"]       = "tenant"
    result["tenant_name"] = t.name
    result["currency"]   = t.currency
    result["categories"] = db.query(Category).filter(Category.tenant_id == tenant_id).count()
    result["locations"]  = db.query(Location).filter(Location.tenant_id == tenant_id).count()
    result["employees"]  = db.query(Employee).filter(Employee.tenant_id == tenant_id).count()
    return result


@router.get("/stats")
def stats(db: Session = Depends(get_db),
          cu: CurrentUser = Depends(get_current_user),
          tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.view")

    if cu.is_msp_staff and tenant_id is None:
        # MSP root dashboard — aggregate across all tenants
        tenants = db.query(Tenant).filter(Tenant.active == True).all()
        all_assets = db.query(Asset).count()
        all_value  = db.query(func.coalesce(func.sum(Asset.purchase_cost), 0)).scalar() or 0
        soon = date.today() + timedelta(days=30)
        all_expiring = db.query(Asset).filter(
            Asset.warranty_expiry != None,
            Asset.warranty_expiry <= soon,
            Asset.warranty_expiry >= date.today()).count()
        client_summaries = []
        for t in tenants:
            ta = db.query(Asset).filter(Asset.tenant_id == t.id).count()
            td = db.query(Asset).filter(Asset.tenant_id == t.id,
                                         Asset.status == "deployed").count()
            tv = db.query(func.coalesce(func.sum(Asset.purchase_cost), 0))\
                   .filter(Asset.tenant_id == t.id).scalar() or 0
            exp = db.query(Asset).filter(Asset.tenant_id == t.id,
                                          Asset.warranty_expiry != None,
                                          Asset.warranty_expiry <= soon,
                                          Asset.warranty_expiry >= date.today()).count()
            client_summaries.append({
                "id": t.id, "name": t.name, "slug": t.slug,
                "total_assets": ta, "deployed": td,
                "total_value": round(tv, 2), "expiring_warranties": exp,
            })
        return {
            "mode": "msp",
            "total_clients": len(tenants),
            "total_assets": all_assets,
            "total_value": round(all_value, 2),
            "expiring_soon": all_expiring,
            "clients": client_summaries,
        }

    # Single-tenant stats
    if tenant_id is None:
        return {"mode": "empty"}
    result = _tenant_stats(db, tenant_id)
    result["mode"] = "tenant"
    t = db.query(Tenant).get(tenant_id)
    result["tenant_name"] = t.name if t else ""
    result["currency"] = t.currency if t else "USD"
    result["categories"] = db.query(Category).filter(Category.tenant_id == tenant_id).count()
    result["locations"]  = db.query(Location).filter(Location.tenant_id == tenant_id).count()
    result["employees"]  = db.query(Employee).filter(Employee.tenant_id == tenant_id).count()
    return result
