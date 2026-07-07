import base64, csv, io, math, os, uuid
from datetime import datetime
from typing import List, Optional
import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi import UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, literal, union_all, text as sa_text

import audit
from db.database import get_db
from billing import is_saas, usage_status
from models.models import MspBilling
from models.models import Asset, AssetNote, AssetCheckinToken, AssetPhoto, AssetMaintenance, Category, Location, Employee, CheckoutLog, Tenant, TenantDomain, AuditLog
from schemas.schemas import AssetIn, AssetOut, CheckoutIn, HistoryOut
from security import get_current_user, CurrentUser, get_tenant_id, resolve_tenant_slug

router = APIRouter()


def calculate_depreciation(asset) -> dict | None:
    """
    Returns depreciation info for an asset, or None if insufficient data.
    Requires: purchase_cost, purchase_date, useful_life_years.
    salvage_value defaults to 0 if not set.
    """
    if not asset.purchase_cost or not asset.purchase_date or not asset.useful_life_years:
        return None

    from datetime import date as _date
    salvage = asset.salvage_value or 0.0
    depreciable = asset.purchase_cost - salvage
    if depreciable <= 0:
        return None

    annual_depreciation = depreciable / asset.useful_life_years
    years_owned = (_date.today() - asset.purchase_date).days / 365.25
    total_depreciation = min(annual_depreciation * years_owned, depreciable)
    current_value = round(asset.purchase_cost - total_depreciation, 2)

    try:
        end_of_life = _date(
            asset.purchase_date.year + asset.useful_life_years,
            asset.purchase_date.month,
            asset.purchase_date.day,
        )
    except ValueError:
        # Feb 29 edge case: fall back to Mar 1
        end_of_life = _date(
            asset.purchase_date.year + asset.useful_life_years, 3, 1
        )
    days_remaining = (end_of_life - _date.today()).days
    fully_depreciated = days_remaining <= 0

    return {
        "purchase_cost":       asset.purchase_cost,
        "salvage_value":       salvage,
        "useful_life_years":   asset.useful_life_years,
        "annual_depreciation": round(annual_depreciation, 2),
        "current_value":       max(current_value, salvage),
        "total_depreciation":  round(total_depreciation, 2),
        "depreciation_pct":    round((total_depreciation / depreciable) * 100, 1),
        "end_of_life_date":    str(end_of_life),
        "days_remaining":      days_remaining,
        "fully_depreciated":   fully_depreciated,
    }


def _q(db, tenant_id):
    q = db.query(Asset)
    if tenant_id is not None:
        q = q.filter(Asset.tenant_id == tenant_id)
    return q


def _to_out(a: Asset) -> dict:
    return {
        "id": a.id, "tenant_id": a.tenant_id, "asset_tag": a.asset_tag,
        "name": a.name, "serial": a.serial, "model": a.model,
        "manufacturer": a.manufacturer, "status": a.status, "notes": a.notes,
        "purchase_date": a.purchase_date, "purchase_cost": a.purchase_cost,
        "warranty_expiry": a.warranty_expiry,
        "useful_life_years": a.useful_life_years,
        "salvage_value":     a.salvage_value,
        "category_id": a.category_id, "location_id": a.location_id,
        "assigned_to_id": a.assigned_to_id,
        "created_at": a.created_at, "updated_at": a.updated_at,
        "category_name":    a.category.name if a.category else None,
        "location_name":    a.location.name if a.location else None,
        "assigned_to_name": a.assigned_to.name if a.assigned_to else None,
    }


@router.get("")
def list_assets(q: Optional[str] = None, status: Optional[str] = None,
                category_id: Optional[int] = None, location_id: Optional[int] = None,
                department: Optional[str] = None,
                sort: str = "asset_tag", order: str = "asc",
                page: int = Query(1, ge=1),
                limit: int = Query(50, ge=1, le=200),
                db: Session = Depends(get_db),
                cu: CurrentUser = Depends(get_current_user),
                tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.view")
    query = _q(db, tenant_id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Asset.asset_tag.ilike(like), Asset.name.ilike(like),
                                  Asset.serial.ilike(like), Asset.model.ilike(like),
                                  Asset.manufacturer.ilike(like)))
    if status:      query = query.filter(Asset.status == status)
    if category_id: query = query.filter(Asset.category_id == category_id)
    if location_id: query = query.filter(Asset.location_id == location_id)
    if department:
        query = query.join(Employee, Asset.assigned_to_id == Employee.id).filter(
            Employee.department == department
        )
    col = getattr(Asset, sort, Asset.asset_tag)
    query = query.order_by(col.desc() if order == "desc" else col.asc())
    total = query.count()
    items = [_to_out(a) for a in query.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit,
            "pages": max(1, math.ceil(total / limit))}


@router.get("/export/csv")
def export_csv(db: Session = Depends(get_db),
               cu: CurrentUser = Depends(get_current_user),
               tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.export")
    from models.models import CustomFieldDef, CustomFieldValue

    # Gather all field defs for this tenant so we can add dynamic columns
    cf_defs = []
    if tenant_id is not None:
        cf_defs = (
            db.query(CustomFieldDef)
            .filter(CustomFieldDef.tenant_id == tenant_id)
            .order_by(CustomFieldDef.label)
            .all()
        )

    output = io.StringIO()
    writer = csv.writer(output)
    base_headers = ["asset_tag","name","serial","model","manufacturer","status",
                    "category","location","assigned_to","purchase_date",
                    "purchase_cost","warranty_expiry","notes"]
    writer.writerow(base_headers + [d.label for d in cf_defs])

    # Build a lookup of {asset_id: {field_def_id: value}} for efficiency
    cf_lookup: dict = {}
    if cf_defs:
        rows = (
            db.query(CustomFieldValue)
            .filter(CustomFieldValue.field_def_id.in_([d.id for d in cf_defs]))
            .all()
        )
        for row in rows:
            cf_lookup.setdefault(row.asset_id, {})[row.field_def_id] = row.value

    for a in _q(db, tenant_id).all():
        base_row = [
            a.asset_tag, a.name, a.serial, a.model, a.manufacturer, a.status,
            a.category.name if a.category else "",
            a.location.name if a.location else "",
            a.assigned_to.name if a.assigned_to else "",
            a.purchase_date or "", a.purchase_cost if a.purchase_cost is not None else "",
            a.warranty_expiry or "", a.notes,
        ]
        cf_row = [cf_lookup.get(a.id, {}).get(d.id, "") for d in cf_defs]
        writer.writerow(base_row + cf_row)

    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=assets.csv"})


def _parse_csv_rows(content: str, tenant_id: int, db):
    """
    Parse CSV content and return (creates, updates, errors, cf_new_defs).
    Does NOT commit anything — pure analysis.
    """
    from models.models import CustomFieldDef
    reader = csv.DictReader(io.StringIO(content))

    _KNOWN_COLS = {
        "asset_tag","name","serial","model","manufacturer","status",
        "category","location","assigned_to","purchase_date",
        "purchase_cost","warranty_expiry","notes",
    }

    def parse_date(v):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try: return datetime.strptime((v or "").strip(), fmt).strftime("%Y-%m-%d")
            except ValueError: pass
        return None

    def parse_cost(v):
        try: return float(str(v).replace(",","").replace("$","").strip())
        except: return None

    # Custom field columns
    cf_cols = []
    new_cf_defs = []
    if reader.fieldnames:
        for col in reader.fieldnames:
            if col and col not in _KNOWN_COLS:
                cf_cols.append(col)
                fd = db.query(CustomFieldDef).filter(
                    CustomFieldDef.tenant_id == tenant_id,
                    CustomFieldDef.label == col,
                ).first()
                if not fd:
                    new_cf_defs.append(col)

    creates, updates, errors = [], [], []

    for i, row in enumerate(reader, start=2):
        tag = (row.get("asset_tag") or "").strip()
        if not tag:
            errors.append({"row": i, "error": "missing asset_tag"})
            continue

        status = (row.get("status") or "available").strip() or "available"
        if status not in _VALID_STATUSES:
            errors.append({"row": i, "asset_tag": tag, "error": f"invalid status '{status}'"})

        record = {
            "asset_tag":     tag,
            "name":          (row.get("name") or tag).strip(),
            "serial":        (row.get("serial") or "").strip(),
            "model":         (row.get("model") or "").strip(),
            "manufacturer":  (row.get("manufacturer") or "").strip(),
            "status":        status,
            "notes":         (row.get("notes") or "").strip(),
            "category":      (row.get("category") or "").strip(),
            "location":      (row.get("location") or "").strip(),
            "assigned_to":   (row.get("assigned_to") or "").strip(),
            "purchase_date": parse_date(row.get("purchase_date")),
            "purchase_cost": parse_cost(row.get("purchase_cost")),
            "warranty_expiry": parse_date(row.get("warranty_expiry")),
        }
        for col in cf_cols:
            record[f"cf:{col}"] = (row.get(col) or "").strip()

        existing = db.query(Asset).filter(
            Asset.tenant_id == tenant_id, Asset.asset_tag == tag
        ).first()

        if existing:
            # Build a diff: which fields would change
            changes = []
            simple_map = {
                "name": existing.name, "serial": existing.serial,
                "model": existing.model, "manufacturer": existing.manufacturer,
                "status": existing.status, "notes": existing.notes,
            }
            for field, cur_val in simple_map.items():
                new_val = record[field]
                if new_val and new_val != (cur_val or ""):
                    changes.append({"field": field, "from": cur_val or "", "to": new_val})
            updates.append({"row": i, "asset_tag": tag, "name": record["name"],
                            "changes": changes, "change_count": len(changes)})
        else:
            creates.append({"row": i, "asset_tag": tag, "name": record["name"],
                            "category": record["category"], "status": record["status"]})

    return creates, updates, errors, new_cf_defs


_VALID_STATUSES = {"available", "deployed", "maintenance", "retired"}


@router.post("/import/csv/preview")
async def preview_csv_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    """Analyse a CSV and return what would be created/updated/errored — does not commit."""
    cu.require("assets.import")
    if tenant_id is None:
        raise HTTPException(400, "Specify a tenant to import into")

    content = (await file.read()).decode("utf-8-sig")
    creates, updates, errors, new_cf_defs = _parse_csv_rows(content, tenant_id, db)

    return {
        "creates":      creates,
        "updates":      updates,
        "errors":       errors,
        "new_cf_defs":  new_cf_defs,
        "summary": {
            "total_rows": len(creates) + len(updates) + len(errors),
            "creates":    len(creates),
            "updates":    len(updates),
            "errors":     len(errors),
            "new_cf_defs": len(new_cf_defs),
        },
    }


@router.post("/import/csv")
async def import_csv(file: UploadFile = File(...),
                     request: Request = None,
                     db: Session = Depends(get_db),
                     cu: CurrentUser = Depends(get_current_user),
                     tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.import")
    if tenant_id is None:
        raise HTTPException(400, "Specify a tenant to import into")
    # ── Tier limit check (SaaS only) ──
    if is_saas():
        billing = db.query(MspBilling).first()
        tier_key = billing.tier if billing else "trial"
        total = db.query(Asset).count()
        us = usage_status(total, tier_key)
        if us["status"] == "exceeded":
            raise HTTPException(402, f"Asset limit reached for your {tier_key.title()} plan. Please upgrade.")
    from models.models import CustomFieldDef, CustomFieldValue

    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    created, updated, errors = 0, 0, []

    _KNOWN_COLS = {
        "asset_tag","name","serial","model","manufacturer","status",
        "category","location","assigned_to","purchase_date",
        "purchase_cost","warranty_expiry","notes",
    }

    # Build label→def mapping for unknown columns, creating defs when missing
    cf_col_map: dict = {}   # csv_header → CustomFieldDef
    if reader.fieldnames:
        for col in reader.fieldnames:
            if col and col not in _KNOWN_COLS:
                fd = db.query(CustomFieldDef).filter(
                    CustomFieldDef.tenant_id == tenant_id,
                    CustomFieldDef.label == col,
                ).first()
                if not fd:
                    fd = CustomFieldDef(tenant_id=tenant_id, label=col, field_type="text")
                    db.add(fd)
                    db.flush()
                cf_col_map[col] = fd

    def _get_or_create(model, name):
        if not name: return None
        obj = db.query(model).filter(model.tenant_id == tenant_id, model.name == name).first()
        if not obj:
            obj = model(tenant_id=tenant_id, name=name)
            db.add(obj); db.flush()
        return obj

    for i, row in enumerate(reader, start=2):
        tag = (row.get("asset_tag") or "").strip()
        if not tag: errors.append(f"Row {i}: missing asset_tag"); continue
        cat = _get_or_create(Category, (row.get("category") or "").strip())
        loc = _get_or_create(Location, (row.get("location") or "").strip())
        emp_name = (row.get("assigned_to") or "").strip()
        emp = None
        if emp_name:
            emp = db.query(Employee).filter(Employee.tenant_id == tenant_id,
                                             Employee.name == emp_name).first()
            if not emp:
                emp = Employee(tenant_id=tenant_id, name=emp_name); db.add(emp); db.flush()

        def parse_date(v):
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try: return datetime.strptime((v or "").strip(), fmt).date()
                except ValueError: pass
            return None

        def parse_cost(v):
            try: return float(str(v).replace(",","").replace("$","").strip())
            except: return None

        fields = dict(name=(row.get("name") or tag).strip(),
                      serial=(row.get("serial") or "").strip(),
                      model=(row.get("model") or "").strip(),
                      manufacturer=(row.get("manufacturer") or "").strip(),
                      status=(row.get("status") or "available").strip() or "available",
                      notes=(row.get("notes") or "").strip(),
                      purchase_date=parse_date(row.get("purchase_date")),
                      purchase_cost=parse_cost(row.get("purchase_cost")),
                      warranty_expiry=parse_date(row.get("warranty_expiry")),
                      category_id=cat.id if cat else None,
                      location_id=loc.id if loc else None,
                      assigned_to_id=emp.id if emp else None)
        existing = db.query(Asset).filter(Asset.tenant_id == tenant_id,
                                           Asset.asset_tag == tag).first()
        if existing:
            for k, v in fields.items(): setattr(existing, k, v)
            asset_obj = existing
            updated += 1
        else:
            asset_obj = Asset(tenant_id=tenant_id, asset_tag=tag, **fields)
            db.add(asset_obj)
            db.flush()
            created += 1

        # Upsert custom field values for unknown columns
        for col, fd in cf_col_map.items():
            val = (row.get(col) or "").strip()
            cfv = db.query(CustomFieldValue).filter(
                CustomFieldValue.field_def_id == fd.id,
                CustomFieldValue.asset_id == asset_obj.id,
            ).first()
            if cfv:
                cfv.value = val
            else:
                db.add(CustomFieldValue(field_def_id=fd.id, asset_id=asset_obj.id, value=val))

    db.commit()
    audit.log(db, "asset.import", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tenant_id,
              resource="asset",
              detail=f"Imported {created} created, {updated} updated",
              ip_address=request.client.host if request and request.client else "")
    return {"created": created, "updated": updated, "errors": errors}


_VALID_STATUSES = {"available", "deployed", "maintenance", "retired"}


class BulkStatusBody(BaseModel):
    asset_ids: List[int]
    status: str


class BulkLocationBody(BaseModel):
    asset_ids: List[int]
    location_id: int


class BulkDeleteBody(BaseModel):
    asset_ids: List[int]


@router.post("/bulk/status")
def bulk_status(body: BulkStatusBody, request: Request,
                db: Session = Depends(get_db),
                cu: CurrentUser = Depends(get_current_user),
                tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.edit")
    if body.status not in _VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(sorted(_VALID_STATUSES))}")
    updated, skipped = 0, 0
    for aid in body.asset_ids:
        a = db.query(Asset).get(aid)
        if a is None or (tenant_id is not None and a.tenant_id != tenant_id):
            skipped += 1
            continue
        a.status = body.status
        updated += 1
    db.commit()
    if updated:
        audit.log(db, "asset.bulk_status", actor_id=cu.id, actor_email=cu.email,
                  actor_name=cu.name, tenant_id=tenant_id,
                  resource="asset", detail=f"Bulk set status={body.status} on {updated} assets",
                  ip_address=request.client.host if request.client else "")
    return {"updated": updated, "skipped": skipped}


@router.post("/bulk/location")
def bulk_location(body: BulkLocationBody, request: Request,
                  db: Session = Depends(get_db),
                  cu: CurrentUser = Depends(get_current_user),
                  tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.edit")
    loc = db.query(Location).get(body.location_id)
    if loc is None or (tenant_id is not None and loc.tenant_id != tenant_id):
        raise HTTPException(400, "Location not found or does not belong to this tenant")
    updated, skipped = 0, 0
    for aid in body.asset_ids:
        a = db.query(Asset).get(aid)
        if a is None or (tenant_id is not None and a.tenant_id != tenant_id):
            skipped += 1
            continue
        a.location_id = body.location_id
        updated += 1
    db.commit()
    if updated:
        audit.log(db, "asset.bulk_location", actor_id=cu.id, actor_email=cu.email,
                  actor_name=cu.name, tenant_id=tenant_id,
                  resource="asset", detail=f"Bulk set location_id={body.location_id} on {updated} assets",
                  ip_address=request.client.host if request.client else "")
    return {"updated": updated, "skipped": skipped}


@router.post("/bulk/delete")
def bulk_delete(body: BulkDeleteBody, request: Request,
                db: Session = Depends(get_db),
                cu: CurrentUser = Depends(get_current_user),
                tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.delete")
    deleted, skipped = 0, 0
    for aid in body.asset_ids:
        a = db.query(Asset).get(aid)
        if a is None or (tenant_id is not None and a.tenant_id != tenant_id):
            skipped += 1
            continue
        db.delete(a)
        deleted += 1
    db.commit()
    if deleted:
        audit.log(db, "asset.bulk_delete", actor_id=cu.id, actor_email=cu.email,
                  actor_name=cu.name, tenant_id=tenant_id,
                  resource="asset", detail=f"Bulk deleted {deleted} assets",
                  ip_address=request.client.host if request.client else "")
    return {"deleted": deleted, "skipped": skipped}


@router.get("/activity")
def activity_feed(
    limit:    int = Query(50, ge=1, le=200),
    offset:   int = Query(0, ge=0),
    action:   Optional[str] = Query(None),
    asset_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    db:       Session = Depends(get_db),
    cu:       CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.view")

    _action_map = {
        "asset.create": "create",
        "asset.update": "update",
        "asset.delete": "delete",
    }

    # ── Build CheckoutLog sub-query ───────────────────────────────────────────
    cl_q = (
        db.query(CheckoutLog, Asset)
        .join(Asset, CheckoutLog.asset_id == Asset.id)
    )
    if tenant_id is not None:
        cl_q = cl_q.filter(Asset.tenant_id == tenant_id)
    if action in ("checkout", "checkin"):
        cl_q = cl_q.filter(CheckoutLog.action == action)
    elif action in ("create", "update", "delete"):
        cl_q = cl_q.filter(False)
    if asset_id is not None:
        cl_q = cl_q.filter(CheckoutLog.asset_id == asset_id)
    if date_from:
        try:
            cl_q = cl_q.filter(CheckoutLog.timestamp >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            cl_q = cl_q.filter(CheckoutLog.timestamp <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass

    # ── Build AuditLog sub-query ──────────────────────────────────────────────
    al_q = (
        db.query(AuditLog)
        .filter(AuditLog.resource == "asset")
        .filter(AuditLog.action.in_(list(_action_map.keys())))
    )
    if tenant_id is not None:
        al_q = al_q.filter(AuditLog.tenant_id == tenant_id)
    if action in ("create", "update", "delete"):
        reverse = {v: k for k, v in _action_map.items()}
        al_q = al_q.filter(AuditLog.action == reverse[action])
    elif action in ("checkout", "checkin"):
        al_q = al_q.filter(False)
    if asset_id is not None:
        tgt = db.query(Asset).get(asset_id)
        if tgt:
            al_q = al_q.filter(AuditLog.resource_id == tgt.asset_tag)
        else:
            al_q = al_q.filter(False)
    if date_from:
        try:
            al_q = al_q.filter(AuditLog.timestamp >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            al_q = al_q.filter(AuditLog.timestamp <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass

    # ── Count totals from DB ──────────────────────────────────────────────────
    cl_total = cl_q.count()
    try:
        al_total = al_q.count()
    except Exception:
        al_total = 0
    total = cl_total + al_total

    # ── Fetch each source ordered by timestamp, apply window ─────────────────
    # To paginate correctly across two sources we fetch only enough rows from
    # each to satisfy the worst case (all results from one source), then merge
    # the bounded set in Python. This is O(limit+offset) not O(N).
    window = offset + limit

    cl_rows = cl_q.order_by(desc(CheckoutLog.timestamp)).limit(window).all()
    checkout_events = [
        {
            "id":          log_row.id,
            "timestamp":   log_row.timestamp.isoformat() if log_row.timestamp else None,
            "action":      log_row.action,
            "asset_tag":   asset.asset_tag,
            "asset_name":  asset.name,
            "asset_id":    asset.id,
            "actor_name":  log_row.employee_name or "—",
            "actor_type":  "employee",
            "note":        log_row.note or "",
            "tenant_name": asset.tenant.name if asset.tenant else "",
        }
        for log_row, asset in cl_rows
    ]

    audit_events = []
    try:
        al_rows = al_q.order_by(desc(AuditLog.timestamp)).limit(window).all()
        audit_events = [
            {
                "id":          row.id,
                "timestamp":   row.timestamp.isoformat() if row.timestamp else None,
                "action":      _action_map.get(row.action, row.action),
                "asset_tag":   row.resource_id or "",
                "asset_name":  row.detail or "",
                "asset_id":    None,
                "actor_name":  row.actor_name or row.actor_email or "—",
                "actor_type":  "user",
                "note":        row.detail or "",
                "tenant_name": row.tenant_name or "",
            }
            for row in al_rows
        ]
    except Exception:
        pass    # AuditLog table may not exist on older installs

    # ── Merge bounded window, sort, paginate ──────────────────────────────────
    merged = checkout_events + audit_events
    merged.sort(key=lambda e: e["timestamp"] or "", reverse=True)
    page_items = merged[offset: offset + limit]

    return {"items": page_items, "total": total, "limit": limit, "offset": offset}


@router.get("/public/checkin/{token}")
def public_checkin_info(token: str, db: Session = Depends(get_db)):
    """Return asset info for a check-in token (no auth required)."""
    ct = db.query(AssetCheckinToken).filter(AssetCheckinToken.token == token).first()
    if not ct:
        raise HTTPException(404, "Check-in link not found or already used")
    if ct.used_at:
        raise HTTPException(410, "This check-in link has already been used")
    if ct.expires_at < datetime.utcnow():
        raise HTTPException(410, "This check-in link has expired")
    asset = ct.asset
    return {
        "asset_tag": asset.asset_tag,
        "asset_name": asset.name,
        "status": asset.status,
        "assigned_to": asset.assigned_to.name if asset.assigned_to else None,
    }


@router.post("/public/checkin/{token}")
def public_checkin_submit(token: str, db: Session = Depends(get_db)):
    """Check in an asset using a single-use public token (no auth required)."""
    ct = db.query(AssetCheckinToken).filter(AssetCheckinToken.token == token).first()
    if not ct:
        raise HTTPException(404, "Check-in link not found or already used")
    if ct.used_at:
        raise HTTPException(410, "This check-in link has already been used")
    if ct.expires_at < datetime.utcnow():
        raise HTTPException(410, "This check-in link has expired")
    asset = ct.asset
    prev_name = asset.assigned_to.name if asset.assigned_to else ""
    asset.assigned_to_id = None
    asset.status = "available"
    ct.used_at = datetime.utcnow()
    db.add(CheckoutLog(
        asset_id=asset.id, employee_id=None,
        employee_name=prev_name or "", action="checkin",
        note="Self-service check-in via public link",
    ))
    db.commit()
    return {"ok": True, "asset_tag": asset.asset_tag, "asset_name": asset.name}


@router.get("/{asset_id}")
def get_asset(asset_id: int, db: Session = Depends(get_db),
              cu: CurrentUser = Depends(get_current_user),
              tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.view")
    a = _q(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404, "Asset not found")
    result = _to_out(a)
    result["depreciation"] = calculate_depreciation(a)
    from routers.custom_fields import get_custom_field_values
    result["custom_fields"] = get_custom_field_values(a.id, db, a.tenant_id)
    return result


@router.post("")
def create_asset(body: AssetIn, request: Request,
                 db: Session = Depends(get_db),
                 cu: CurrentUser = Depends(get_current_user),
                 tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.create")
    if tenant_id is None: raise HTTPException(400, "Specify a tenant")
    if db.query(Asset).filter(Asset.tenant_id == tenant_id,
                               Asset.asset_tag == body.asset_tag).first():
        raise HTTPException(400, "Asset tag already exists in this tenant")
    # ── Tier limit check (SaaS only) ──
    if is_saas():
        billing = db.query(MspBilling).first()
        tier_key = billing.tier if billing else "trial"
        total = db.query(Asset).count()
        us = usage_status(total, tier_key)
        if us["status"] == "exceeded":
            raise HTTPException(402, f"Asset limit reached for your {tier_key.title()} plan "
                                     f"({total}/{us['limit']} assets). Please upgrade to add more.")
    a = Asset(tenant_id=tenant_id, **body.model_dump())
    db.add(a); db.commit(); db.refresh(a)
    audit.log(db, "asset.create", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tenant_id,
              resource="asset", resource_id=a.asset_tag,
              detail=f"Created {a.name}",
              ip_address=request.client.host if request.client else "")
    from webhook_service import fire as _wh_fire
    _wh_fire(a.tenant, "asset.created", {"asset_tag": a.asset_tag, "name": a.name, "status": a.status})
    return _to_out(a)


@router.put("/{asset_id}")
def update_asset(asset_id: int, body: AssetIn, request: Request,
                 db: Session = Depends(get_db),
                 cu: CurrentUser = Depends(get_current_user),
                 tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.edit")
    a = _q(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404, "Asset not found")
    dup = db.query(Asset).filter(Asset.tenant_id == a.tenant_id,
                                  Asset.asset_tag == body.asset_tag,
                                  Asset.id != asset_id).first()
    if dup: raise HTTPException(400, "Asset tag already exists")
    for k, v in body.model_dump().items(): setattr(a, k, v)
    db.commit(); db.refresh(a)
    audit.log(db, "asset.update", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tenant_id,
              resource="asset", resource_id=a.asset_tag,
              detail=f"Updated {a.name}",
              ip_address=request.client.host if request.client else "")
    from webhook_service import fire as _wh_fire
    _wh_fire(a.tenant, "asset.updated", {"asset_tag": a.asset_tag, "name": a.name, "status": a.status})
    return _to_out(a)


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, request: Request,
                 db: Session = Depends(get_db),
                 cu: CurrentUser = Depends(get_current_user),
                 tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.delete")
    a = _q(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404, "Asset not found")
    tag, name, tid, tenant = a.asset_tag, a.name, a.tenant_id, a.tenant
    db.delete(a); db.commit()
    audit.log(db, "asset.delete", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tid,
              resource="asset", resource_id=tag,
              detail=f"Deleted {name}",
              ip_address=request.client.host if request.client else "")
    from webhook_service import fire as _wh_fire
    _wh_fire(tenant, "asset.deleted", {"asset_tag": tag, "name": name})
    return {"ok": True}


@router.post("/{asset_id}/checkout")
def checkout(asset_id: int, body: CheckoutIn, request: Request,
             db: Session = Depends(get_db),
             cu: CurrentUser = Depends(get_current_user),
             tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.checkout")
    a = _q(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404, "Asset not found")
    if a.status == "deployed": raise HTTPException(400, "Asset is already checked out")
    emp = db.query(Employee).get(body.employee_id) if body.employee_id else None
    emp_name = emp.name if emp else ""
    a.assigned_to_id = body.employee_id; a.status = "deployed"
    db.add(CheckoutLog(asset_id=a.id, employee_id=body.employee_id,
                       employee_name=emp_name, action="checkout", note=body.note))
    db.commit(); db.refresh(a)
    audit.log(db, "asset.checkout", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tenant_id,
              resource="asset", resource_id=a.asset_tag,
              detail=f"Checked out to {emp_name}",
              ip_address=request.client.host if request.client else "")
    return _to_out(a)


@router.post("/{asset_id}/checkin")
def checkin(asset_id: int, body: CheckoutIn, request: Request,
            db: Session = Depends(get_db),
            cu: CurrentUser = Depends(get_current_user),
            tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.checkin")
    a = _q(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404, "Asset not found")
    prev = a.assigned_to.name if a.assigned_to else ""
    a.assigned_to_id = None; a.status = "available"
    db.add(CheckoutLog(asset_id=a.id, employee_name=prev, action="checkin", note=body.note))
    db.commit(); db.refresh(a)
    audit.log(db, "asset.checkin", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tenant_id,
              resource="asset", resource_id=a.asset_tag,
              detail=f"Checked in from {prev}",
              ip_address=request.client.host if request.client else "")
    return _to_out(a)


@router.get("/{asset_id}/history")
def history(asset_id: int, db: Session = Depends(get_db),
            cu: CurrentUser = Depends(get_current_user),
            tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.view")
    a = _q(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404, "Asset not found")
    return db.query(CheckoutLog).filter(CheckoutLog.asset_id == asset_id)\
             .order_by(CheckoutLog.timestamp.desc()).all()


class LabelPrintIn(BaseModel):
    asset_ids: List[int]  = Field(..., min_length=1, max_length=100)
    size:      str        = Field("medium", pattern="^(small|medium|large)$")


@router.post("/labels", response_class=HTMLResponse)
def print_labels(
    body: LabelPrintIn,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    """Return a print-ready HTML page of QR label stickers for the given asset IDs."""
    cu.require("assets.view")

    assets = _q(db, tenant_id).filter(Asset.id.in_(body.asset_ids)).all()
    if not assets:
        raise HTTPException(404, "No matching assets found")

    # Sort to preserve requested order
    id_order = {aid: i for i, aid in enumerate(body.asset_ids)}
    assets.sort(key=lambda a: id_order.get(a.id, 9999))

    sizes = {
        "small":  {"px": 120, "font": 9,  "cols": 5},
        "medium": {"px": 160, "font": 11, "cols": 4},
        "large":  {"px": 220, "font": 13, "cols": 3},
    }
    cfg = sizes[body.size]
    sz  = cfg["px"]

    def _qr_svg(text: str) -> str:
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(text, image_factory=factory, box_size=4, border=1)
        buf = io.BytesIO(); img.save(buf)
        return buf.getvalue().decode("utf-8")

    labels_html = ""
    for a in assets:
        svg = _qr_svg(a.asset_tag)
        name = (a.name[:28] + "…") if len(a.name) > 28 else a.name
        labels_html += f"""
        <div class="label">
          <div class="qr">{svg}</div>
          <div class="tag">{a.asset_tag}</div>
          <div class="name">{name}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Asset Labels</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: monospace; background: #fff; color: #000; }}
  .toolbar {{
    position: fixed; top: 0; left: 0; right: 0; background: #f5f5f5;
    border-bottom: 1px solid #ddd; padding: 10px 16px;
    display: flex; align-items: center; gap: 12px; z-index: 99;
  }}
  .toolbar button {{
    padding: 7px 18px; background: #15171c; color: #d4f034;
    border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600;
  }}
  .toolbar span {{ font-size: 12px; color: #666; }}
  @media print {{ .toolbar {{ display: none; }} }}
  .grid {{
    margin-top: 52px; padding: 12px;
    display: grid;
    grid-template-columns: repeat({cfg["cols"]}, {sz}px);
    gap: 8px;
  }}
  @media print {{
    .grid {{ margin-top: 0; }}
    .label {{ break-inside: avoid; }}
  }}
  .label {{
    width: {sz}px; height: {sz}px;
    border: 1px dashed #bbb; border-radius: 4px;
    padding: 4px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 2px; overflow: hidden;
  }}
  .qr {{ width: {sz - 28}px; height: {sz - 28}px; flex-shrink: 0; }}
  .qr svg {{ width: 100%; height: 100%; }}
  .tag {{ font-size: {cfg["font"]}px; font-weight: bold; text-align: center; word-break: break-all; }}
  .name {{ font-size: {cfg["font"] - 1}px; color: #555; text-align: center;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: {sz - 8}px; }}
</style>
</head>
<body>
<div class="toolbar">
  <button onclick="window.print()">&#128438; Print / Save as PDF</button>
  <span>{len(assets)} label(s) · {body.size} size</span>
</div>
<div class="grid">{labels_html}</div>
</body>
</html>"""
    return HTMLResponse(content=html)


class NoteIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)


# ── Public check-in token ─────────────────────────────────────────────────────
import secrets


@router.post("/{asset_id}/checkin-token")
def generate_checkin_token(
    asset_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    """Generate a single-use public check-in link token for this asset."""
    cu.require("assets.edit")
    asset = db.query(Asset).get(asset_id)
    if not asset or (tenant_id is not None and asset.tenant_id != tenant_id):
        raise HTTPException(404, "Asset not found")
    # Invalidate any existing unused tokens for this asset
    db.query(AssetCheckinToken).filter(
        AssetCheckinToken.asset_id == asset_id,
        AssetCheckinToken.used_at.is_(None),
    ).delete(synchronize_session=False)
    token_val = secrets.token_urlsafe(32)
    ct = AssetCheckinToken(
        token=token_val,
        asset_id=asset_id,
        tenant_id=asset.tenant_id,
        expires_at=datetime.utcnow() + __import__("datetime").timedelta(days=7),
    )
    db.add(ct)
    db.commit()
    return {"token": token_val, "asset_tag": asset.asset_tag, "asset_name": asset.name}




@router.get("/{asset_id}/notes")
def list_notes(
    asset_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.view")
    asset = db.query(Asset).get(asset_id)
    if not asset or (tenant_id is not None and asset.tenant_id != tenant_id):
        raise HTTPException(404, "Asset not found")
    return [
        {
            "id":          n.id,
            "body":        n.body,
            "author_name": n.author_name or "Unknown",
            "created_at":  n.created_at.isoformat() if n.created_at else None,
        }
        for n in asset.notes_log
    ]


@router.post("/{asset_id}/notes")
def add_note(
    asset_id: int,
    body: NoteIn,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.edit")
    asset = db.query(Asset).get(asset_id)
    if not asset or (tenant_id is not None and asset.tenant_id != tenant_id):
        raise HTTPException(404, "Asset not found")
    note = AssetNote(
        asset_id=asset_id,
        tenant_id=asset.tenant_id,
        author_id=cu.id,
        author_name=cu.name or cu.email,
        body=body.body.strip(),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {
        "id":          note.id,
        "body":        note.body,
        "author_name": note.author_name,
        "created_at":  note.created_at.isoformat() if note.created_at else None,
    }


@router.delete("/{asset_id}/notes/{note_id}")
def delete_note(
    asset_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.edit")
    note = db.query(AssetNote).get(note_id)
    if not note or note.asset_id != asset_id:
        raise HTTPException(404, "Note not found")
    if tenant_id is not None and note.tenant_id != tenant_id:
        raise HTTPException(404, "Note not found")
    db.delete(note)
    db.commit()
    return {"ok": True}


_UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "uploads"
)
_ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10 MB


@router.get("/{asset_id}/photos")
def list_photos(
    asset_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.view")
    asset = db.query(Asset).get(asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    if tenant_id is not None and asset.tenant_id != tenant_id:
        raise HTTPException(404, "Asset not found")
    return [{"id": p.id, "url": f"/uploads/{p.filename}", "created_at": p.created_at.isoformat()}
            for p in asset.photos]


@router.post("/{asset_id}/photos")
async def upload_photo(
    asset_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.edit")
    asset = db.query(Asset).get(asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    if tenant_id is not None and asset.tenant_id != tenant_id:
        raise HTTPException(404, "Asset not found")
    if file.content_type not in _ALLOWED_PHOTO_TYPES:
        raise HTTPException(400, "Unsupported file type. Upload a JPEG, PNG, GIF or WebP image.")
    data = await file.read()
    if len(data) > _MAX_PHOTO_BYTES:
        raise HTTPException(400, "File too large. Maximum size is 10 MB.")
    ext = (file.filename or "photo").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
        ext = "jpg"
    unique_name = f"{asset.tenant_id}_{asset_id}_{uuid.uuid4().hex}.{ext}"
    os.makedirs(_UPLOADS_DIR, exist_ok=True)
    with open(os.path.join(_UPLOADS_DIR, unique_name), "wb") as fh:
        fh.write(data)
    photo = AssetPhoto(asset_id=asset_id, tenant_id=asset.tenant_id, filename=unique_name)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return {"id": photo.id, "url": f"/uploads/{unique_name}", "created_at": photo.created_at.isoformat()}


@router.delete("/{asset_id}/photos/{photo_id}")
def delete_photo(
    asset_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.edit")
    photo = db.query(AssetPhoto).get(photo_id)
    if not photo or photo.asset_id != asset_id:
        raise HTTPException(404, "Photo not found")
    if tenant_id is not None and photo.tenant_id != tenant_id:
        raise HTTPException(404, "Photo not found")
    filepath = os.path.join(_UPLOADS_DIR, photo.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.delete(photo)
    db.commit()
    return {"ok": True}


class MaintenanceIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    maintenance_type: str = Field("", max_length=80)
    due_date: str = Field(...)  # ISO date string
    assigned_to_id: Optional[int] = None
    notes: str = ""


def _asset_for_write(asset_id: int, tenant_id, db: Session):
    asset = db.query(Asset).get(asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    if tenant_id is not None and asset.tenant_id != tenant_id:
        raise HTTPException(404, "Asset not found")
    return asset


@router.get("/{asset_id}/maintenance")
def list_maintenance(
    asset_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.view")
    asset = _asset_for_write(asset_id, tenant_id, db)
    from datetime import date as _date
    today = _date.today()
    result = []
    for m in asset.maintenance_schedules:
        status = m.status
        if status == "scheduled" and m.due_date < today:
            status = "overdue"
            m.status = "overdue"
            db.add(m)
    db.commit()
    return [
        {
            "id": m.id,
            "title": m.title,
            "maintenance_type": m.maintenance_type,
            "due_date": m.due_date.isoformat(),
            "assigned_to_id": m.assigned_to_id,
            "assigned_to_name": m.assigned_to.name if m.assigned_to else None,
            "notes": m.notes,
            "status": m.status,
            "completed_at": m.completed_at.isoformat() if m.completed_at else None,
            "created_at": m.created_at.isoformat(),
        }
        for m in asset.maintenance_schedules
    ]


@router.post("/{asset_id}/maintenance")
def create_maintenance(
    asset_id: int,
    body: MaintenanceIn,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.edit")
    asset = _asset_for_write(asset_id, tenant_id, db)
    try:
        from datetime import date as _date
        due = _date.fromisoformat(body.due_date)
    except ValueError:
        raise HTTPException(400, "Invalid due_date format. Use YYYY-MM-DD.")
    m = AssetMaintenance(
        asset_id=asset_id,
        tenant_id=asset.tenant_id,
        title=body.title,
        maintenance_type=body.maintenance_type,
        due_date=due,
        assigned_to_id=body.assigned_to_id,
        notes=body.notes,
        status="scheduled",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "title": m.title, "due_date": m.due_date.isoformat(), "status": m.status}


@router.patch("/{asset_id}/maintenance/{maintenance_id}/complete")
def complete_maintenance(
    asset_id: int,
    maintenance_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.edit")
    _asset_for_write(asset_id, tenant_id, db)
    m = db.query(AssetMaintenance).get(maintenance_id)
    if not m or m.asset_id != asset_id:
        raise HTTPException(404, "Maintenance record not found")
    m.status = "done"
    m.completed_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "status": "done"}


@router.delete("/{asset_id}/maintenance/{maintenance_id}")
def delete_maintenance(
    asset_id: int,
    maintenance_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.edit")
    _asset_for_write(asset_id, tenant_id, db)
    m = db.query(AssetMaintenance).get(maintenance_id)
    if not m or m.asset_id != asset_id:
        raise HTTPException(404, "Maintenance record not found")
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.get("/{asset_id}/qr")
def qr_code(asset_id: int, request: Request, db: Session = Depends(get_db)):
    slug = resolve_tenant_slug(request)
    if not slug:
        raise HTTPException(404, "Asset not found")
    tenant = (
        db.query(Tenant).filter(Tenant.slug == slug).first() or
        db.query(TenantDomain)
        .filter(TenantDomain.domain == slug, TenantDomain.verified.is_(True))
        .first()
    )
    if not tenant:
        raise HTTPException(404, "Asset not found")
    tenant_id = tenant.tenant_id if isinstance(tenant, TenantDomain) else tenant.id
    a = _q(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    img = qrcode.make(a.asset_tag)
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return StreamingResponse(buf, media_type="image/png",
                             headers={"Content-Disposition": f'inline; filename="{a.asset_tag}.png"'})
