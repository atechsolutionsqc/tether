"""
routers/reports.py — Asset reporting endpoints.

All endpoints require reports.view and are scoped to the requesting tenant
(or all tenants for MSP staff at the root domain).
"""
import csv
import io
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.database import get_db
from models.models import Asset, Category, Location, Employee, Tenant
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()


def _asset_query(db: Session, tenant_id: Optional[int]):
    q = db.query(Asset)
    if tenant_id is not None:
        q = q.filter(Asset.tenant_id == tenant_id)
    return q


@router.get("/warranty")
def warranty_report(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("reports.view")
    cutoff = date.today() + timedelta(days=days)
    today = date.today()
    q = _asset_query(db, tenant_id).filter(
        Asset.warranty_expiry.isnot(None),
        Asset.warranty_expiry <= cutoff,
        Asset.warranty_expiry >= today,
    ).order_by(Asset.warranty_expiry.asc())
    return [
        {
            "asset_tag":       a.asset_tag,
            "name":            a.name,
            "manufacturer":    a.manufacturer,
            "warranty_expiry": a.warranty_expiry.isoformat() if a.warranty_expiry else None,
            "days_remaining":  (a.warranty_expiry - today).days if a.warranty_expiry else None,
            "tenant_name":     a.tenant.name if a.tenant else None,
            "location_name":   a.location.name if a.location else None,
            "assigned_to_name": a.assigned_to.name if a.assigned_to else None,
            "purchase_cost":   a.purchase_cost,
        }
        for a in q.all()
    ]


@router.get("/assets-by-status")
def assets_by_status(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("reports.view")
    statuses = ("available", "deployed", "maintenance", "retired")

    base_q = _asset_query(db, tenant_id)
    summary = {s: base_q.filter(Asset.status == s).count() for s in statuses}
    summary["total"] = sum(summary.values())

    by_tenant = None
    if cu.is_msp_staff and tenant_id is None:
        tenants = db.query(Tenant).order_by(Tenant.name).all()
        by_tenant = []
        for t in tenants:
            row = {"tenant_name": t.name}
            tq = db.query(Asset).filter(Asset.tenant_id == t.id)
            for s in statuses:
                row[s] = tq.filter(Asset.status == s).count()
            row["total"] = sum(row[s] for s in statuses)
            by_tenant.append(row)

    result = {"summary": summary}
    if by_tenant is not None:
        result["by_tenant"] = by_tenant
    return result


@router.get("/value")
def value_report(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("reports.view")
    base_q = _asset_query(db, tenant_id).filter(Asset.purchase_cost.isnot(None))

    total_value = db.query(func.sum(Asset.purchase_cost))
    if tenant_id is not None:
        total_value = total_value.filter(Asset.tenant_id == tenant_id)
    total_value = total_value.scalar() or 0.0

    # by_category
    cats = db.query(Category)
    if tenant_id is not None:
        cats = cats.filter(Category.tenant_id == tenant_id)
    by_category = []
    for cat in cats.order_by(Category.name).all():
        cq = base_q.filter(Asset.category_id == cat.id)
        count = cq.count()
        val = db.query(func.sum(Asset.purchase_cost)).filter(
            Asset.category_id == cat.id,
            Asset.purchase_cost.isnot(None),
        )
        if tenant_id is not None:
            val = val.filter(Asset.tenant_id == tenant_id)
        val = val.scalar() or 0.0
        by_category.append({
            "category_name": cat.name,
            "count":         count,
            "total_value":   round(val, 2),
            "avg_value":     round(val / count, 2) if count else 0.0,
        })
    # uncategorised bucket
    unc_q = base_q.filter(Asset.category_id.is_(None))
    unc_count = unc_q.count()
    if unc_count:
        unc_val = db.query(func.sum(Asset.purchase_cost)).filter(
            Asset.category_id.is_(None),
            Asset.purchase_cost.isnot(None),
        )
        if tenant_id is not None:
            unc_val = unc_val.filter(Asset.tenant_id == tenant_id)
        unc_val = unc_val.scalar() or 0.0
        by_category.append({
            "category_name": "Uncategorised",
            "count":         unc_count,
            "total_value":   round(unc_val, 2),
            "avg_value":     round(unc_val / unc_count, 2),
        })

    by_tenant = None
    if cu.is_msp_staff and tenant_id is None:
        tenants = db.query(Tenant).order_by(Tenant.name).all()
        by_tenant = []
        for t in tenants:
            tv = db.query(func.sum(Asset.purchase_cost)).filter(
                Asset.tenant_id == t.id,
                Asset.purchase_cost.isnot(None),
            ).scalar() or 0.0
            tc = db.query(Asset).filter(Asset.tenant_id == t.id).count()
            by_tenant.append({
                "tenant_name": t.name,
                "count":       tc,
                "total_value": round(tv, 2),
            })

    top_q = _asset_query(db, tenant_id).filter(
        Asset.purchase_cost.isnot(None)
    ).order_by(Asset.purchase_cost.desc()).limit(10)
    top_assets = [
        {
            "asset_tag":    a.asset_tag,
            "name":         a.name,
            "purchase_cost": a.purchase_cost,
            "tenant_name":  a.tenant.name if a.tenant else None,
        }
        for a in top_q.all()
    ]

    result = {
        "total_value":  round(total_value, 2),
        "by_category":  by_category,
        "top_assets":   top_assets,
    }
    if by_tenant is not None:
        result["by_tenant"] = by_tenant
    return result


@router.get("/export")
def export_report(
    report_type: str = Query("assets", regex="^(warranty|assets|value)$"),
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("reports.view")
    today = date.today()
    output = io.StringIO()
    writer = csv.writer(output)
    fname = f"tether-report-{report_type}-{today.isoformat()}.csv"

    if report_type == "warranty":
        writer.writerow(["asset_tag", "name", "manufacturer", "warranty_expiry",
                         "days_remaining", "tenant", "location", "assigned_to", "purchase_cost"])
        cutoff = today + timedelta(days=days)
        rows = _asset_query(db, tenant_id).filter(
            Asset.warranty_expiry.isnot(None),
            Asset.warranty_expiry <= cutoff,
            Asset.warranty_expiry >= today,
        ).order_by(Asset.warranty_expiry.asc()).all()
        for a in rows:
            writer.writerow([
                a.asset_tag, a.name, a.manufacturer or "",
                a.warranty_expiry.isoformat() if a.warranty_expiry else "",
                (a.warranty_expiry - today).days if a.warranty_expiry else "",
                a.tenant.name if a.tenant else "",
                a.location.name if a.location else "",
                a.assigned_to.name if a.assigned_to else "",
                a.purchase_cost if a.purchase_cost is not None else "",
            ])

    elif report_type == "assets":
        writer.writerow(["asset_tag", "name", "status", "category", "location",
                         "assigned_to", "tenant", "serial", "model", "manufacturer",
                         "purchase_date", "purchase_cost", "warranty_expiry"])
        for a in _asset_query(db, tenant_id).order_by(Asset.asset_tag).all():
            writer.writerow([
                a.asset_tag, a.name, a.status,
                a.category.name if a.category else "",
                a.location.name if a.location else "",
                a.assigned_to.name if a.assigned_to else "",
                a.tenant.name if a.tenant else "",
                a.serial or "", a.model or "", a.manufacturer or "",
                a.purchase_date.isoformat() if a.purchase_date else "",
                a.purchase_cost if a.purchase_cost is not None else "",
                a.warranty_expiry.isoformat() if a.warranty_expiry else "",
            ])

    else:  # value
        writer.writerow(["asset_tag", "name", "purchase_cost", "category", "tenant"])
        rows = _asset_query(db, tenant_id).filter(
            Asset.purchase_cost.isnot(None)
        ).order_by(Asset.purchase_cost.desc()).all()
        for a in rows:
            writer.writerow([
                a.asset_tag, a.name, a.purchase_cost,
                a.category.name if a.category else "",
                a.tenant.name if a.tenant else "",
            ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )
