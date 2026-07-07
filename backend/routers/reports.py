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


@router.get("/depreciation")
def depreciation_report(
    fully_depreciated: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("reports.view")
    from routers.assets import calculate_depreciation

    assets = (
        _asset_query(db, tenant_id)
        .filter(
            Asset.purchase_cost.isnot(None),
            Asset.purchase_date.isnot(None),
            Asset.useful_life_years.isnot(None),
        )
        .all()
    )

    items = []
    for a in assets:
        dep = calculate_depreciation(a)
        if dep is None:
            continue
        if fully_depreciated is not None and dep["fully_depreciated"] != fully_depreciated:
            continue
        items.append({
            "asset_id":           a.id,
            "asset_tag":          a.asset_tag,
            "name":               a.name,
            "category_name":      a.category.name if a.category else None,
            "location_name":      a.location.name if a.location else None,
            "purchase_cost":      dep["purchase_cost"],
            "current_value":      dep["current_value"],
            "total_depreciation": dep["total_depreciation"],
            "depreciation_pct":   dep["depreciation_pct"],
            "end_of_life_date":   dep["end_of_life_date"],
            "fully_depreciated":  dep["fully_depreciated"],
            "annual_depreciation": dep["annual_depreciation"],
            "useful_life_years":  dep["useful_life_years"],
        })

    items.sort(key=lambda x: x["depreciation_pct"], reverse=True)

    total_purchase  = round(sum(i["purchase_cost"]  for i in items), 2)
    total_current   = round(sum(i["current_value"]   for i in items), 2)
    total_depr      = round(sum(i["total_depreciation"] for i in items), 2)
    fully_depr_count = sum(1 for i in items if i["fully_depreciated"])

    return {
        "items": items,
        "summary": {
            "total_purchase_value":    total_purchase,
            "total_current_value":     total_current,
            "total_depreciated":       total_depr,
            "fully_depreciated_count": fully_depr_count,
            "tracked_asset_count":     len(items),
        },
    }


@router.get("/depreciation/export")
def depreciation_export(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("reports.view")
    from routers.assets import calculate_depreciation

    assets = (
        _asset_query(db, tenant_id)
        .filter(
            Asset.purchase_cost.isnot(None),
            Asset.purchase_date.isnot(None),
            Asset.useful_life_years.isnot(None),
        )
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "asset_tag", "name", "category", "location",
        "purchase_cost", "salvage_value", "useful_life_years",
        "annual_depreciation", "current_value", "total_depreciation",
        "depreciation_pct", "end_of_life_date", "fully_depreciated",
    ])
    for a in assets:
        dep = calculate_depreciation(a)
        if dep is None:
            continue
        writer.writerow([
            a.asset_tag, a.name,
            a.category.name if a.category else "",
            a.location.name if a.location else "",
            dep["purchase_cost"], dep["salvage_value"], dep["useful_life_years"],
            dep["annual_depreciation"], dep["current_value"],
            dep["total_depreciation"], dep["depreciation_pct"],
            dep["end_of_life_date"], dep["fully_depreciated"],
        ])

    output.seek(0)
    fname = f"tether-depreciation-{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/depreciation/schedule/{asset_id}")
def depreciation_schedule(
    asset_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    """Year-by-year depreciation schedule for a single asset."""
    cu.require("reports.view")
    from routers.assets import calculate_depreciation
    a = _asset_query(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a:
        from fastapi import HTTPException
        raise HTTPException(404, "Asset not found")
    dep = calculate_depreciation(a)
    if not dep:
        from fastapi import HTTPException
        raise HTTPException(400, "Asset has insufficient depreciation data")

    salvage = a.salvage_value or 0.0
    depreciable = a.purchase_cost - salvage
    annual = dep["annual_depreciation"]
    rows = []
    for yr in range(1, a.useful_life_years + 1):
        book_value = max(round(a.purchase_cost - annual * yr, 2), salvage)
        accumulated = min(round(annual * yr, 2), depreciable)
        try:
            yr_end = date(a.purchase_date.year + yr, a.purchase_date.month, a.purchase_date.day)
        except ValueError:
            yr_end = date(a.purchase_date.year + yr, 3, 1)
        rows.append({
            "year":              yr,
            "year_end":          yr_end.isoformat(),
            "annual_depreciation": annual,
            "accumulated_depreciation": accumulated,
            "book_value":        book_value,
            "fully_depreciated": yr >= a.useful_life_years,
        })
    return {
        "asset_tag":     a.asset_tag,
        "asset_name":    a.name,
        "purchase_cost": a.purchase_cost,
        "salvage_value": salvage,
        "useful_life_years": a.useful_life_years,
        "purchase_date": a.purchase_date.isoformat(),
        "schedule":      rows,
    }


@router.get("/depreciation/schedule/{asset_id}/export")
def depreciation_schedule_export(
    asset_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("reports.view")
    from routers.assets import calculate_depreciation
    from fastapi import HTTPException
    a = _asset_query(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    dep = calculate_depreciation(a)
    if not dep:
        raise HTTPException(400, "Asset has insufficient depreciation data")

    salvage = a.salvage_value or 0.0
    depreciable = a.purchase_cost - salvage
    annual = dep["annual_depreciation"]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["year", "year_end", "annual_depreciation",
                     "accumulated_depreciation", "book_value", "fully_depreciated"])
    for yr in range(1, a.useful_life_years + 1):
        book_value = max(round(a.purchase_cost - annual * yr, 2), salvage)
        accumulated = min(round(annual * yr, 2), depreciable)
        try:
            yr_end = date(a.purchase_date.year + yr, a.purchase_date.month, a.purchase_date.day)
        except ValueError:
            yr_end = date(a.purchase_date.year + yr, 3, 1)
        writer.writerow([yr, yr_end.isoformat(), annual, accumulated, book_value, yr >= a.useful_life_years])
    output.seek(0)
    fname = f"tether-depreciation-{a.asset_tag}-{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


_AGE_BRACKETS = [
    ("0–1 yr",  0,   1),
    ("1–3 yr",  1,   3),
    ("3–5 yr",  3,   5),
    ("5+ yr",   5, None),
]


@router.get("/age")
def age_report(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("reports.view")
    today = date.today()

    assets = _asset_query(db, tenant_id).filter(Asset.purchase_date.isnot(None)).all()
    assets_no_date = _asset_query(db, tenant_id).filter(Asset.purchase_date.is_(None)).count()

    brackets = {label: [] for label, _, _ in _AGE_BRACKETS}
    for a in assets:
        age_years = (today - a.purchase_date).days / 365.25
        for label, lo, hi in _AGE_BRACKETS:
            if age_years >= lo and (hi is None or age_years < hi):
                brackets[label].append({
                    "id":           a.id,
                    "asset_tag":    a.asset_tag,
                    "name":         a.name,
                    "purchase_date": a.purchase_date.isoformat(),
                    "age_years":    round(age_years, 1),
                    "status":       a.status,
                    "category":     a.category.name if a.category else "",
                    "tenant":       a.tenant.name if a.tenant else "",
                })
                break

    return {
        "brackets": [
            {"label": label, "count": len(brackets[label]), "assets": brackets[label]}
            for label, _, _ in _AGE_BRACKETS
        ],
        "no_purchase_date": assets_no_date,
        "total": len(assets) + assets_no_date,
    }


@router.get("/age/export")
def age_report_export(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("reports.view")
    today = date.today()
    assets = _asset_query(db, tenant_id).filter(Asset.purchase_date.isnot(None)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["asset_tag", "name", "purchase_date", "age_years",
                     "age_bracket", "status", "category", "tenant"])
    for a in assets:
        age_years = (today - a.purchase_date).days / 365.25
        bracket = next(
            label for label, lo, hi in _AGE_BRACKETS
            if age_years >= lo and (hi is None or age_years < hi)
        )
        writer.writerow([
            a.asset_tag, a.name,
            a.purchase_date.isoformat(), round(age_years, 1),
            bracket, a.status,
            a.category.name if a.category else "",
            a.tenant.name if a.tenant else "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tether-report-age-{today.isoformat()}.csv"},
    )


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
