import csv, io, math
from datetime import datetime
from typing import Optional
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi import UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_

import audit
from db.database import get_db
from billing import is_saas, usage_status
from models.models import MspBilling
from models.models import Asset, Category, Location, Employee, CheckoutLog, Tenant, TenantDomain
from schemas.schemas import AssetIn, AssetOut, CheckoutIn, HistoryOut
from security import get_current_user, CurrentUser, get_tenant_id, resolve_tenant_slug

router = APIRouter()


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
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["asset_tag","name","serial","model","manufacturer","status",
                     "category","location","assigned_to","purchase_date",
                     "purchase_cost","warranty_expiry","notes"])
    for a in _q(db, tenant_id).all():
        writer.writerow([a.asset_tag, a.name, a.serial, a.model, a.manufacturer, a.status,
                         a.category.name if a.category else "",
                         a.location.name if a.location else "",
                         a.assigned_to.name if a.assigned_to else "",
                         a.purchase_date or "", a.purchase_cost if a.purchase_cost is not None else "",
                         a.warranty_expiry or "", a.notes])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=assets.csv"})


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
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    created, updated, errors = 0, 0, []

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
            updated += 1
        else:
            db.add(Asset(tenant_id=tenant_id, asset_tag=tag, **fields)); created += 1
    db.commit()
    audit.log(db, "asset.import", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tenant_id,
              resource="asset",
              detail=f"Imported {created} created, {updated} updated",
              ip_address=request.client.host if request and request.client else "")
    return {"created": created, "updated": updated, "errors": errors}


@router.get("/{asset_id}")
def get_asset(asset_id: int, db: Session = Depends(get_db),
              cu: CurrentUser = Depends(get_current_user),
              tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.view")
    a = _q(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404, "Asset not found")
    return _to_out(a)


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
    return _to_out(a)


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, request: Request,
                 db: Session = Depends(get_db),
                 cu: CurrentUser = Depends(get_current_user),
                 tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.delete")
    a = _q(db, tenant_id).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404, "Asset not found")
    tag, name, tid = a.asset_tag, a.name, a.tenant_id
    db.delete(a); db.commit()
    audit.log(db, "asset.delete", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tid,
              resource="asset", resource_id=tag,
              detail=f"Deleted {name}",
              ip_address=request.client.host if request.client else "")
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
