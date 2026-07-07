from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session
from db.database import get_db
from models.models import Employee, Asset, CheckoutLog
from schemas.schemas import EmployeeIn
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()

def _out(e): return {"id":e.id,"name":e.name,"email":e.email,"department":e.department,"asset_count":len(e.assets)}

@router.get("")
def list_employees(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
    q: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    cu.require("assets.view")
    query = db.query(Employee)
    if tenant_id is not None:
        query = query.filter(Employee.tenant_id == tenant_id)
    if q:
        query = query.filter(Employee.name.ilike(f"%{q}%"))
    total = query.count()
    items = query.order_by(Employee.name).offset(offset).limit(limit).all()
    return {"items": [_out(e) for e in items], "total": total, "limit": limit, "offset": offset}


@router.get("/departments")
def list_departments(db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
                     tenant_id: Optional[int] = Depends(get_tenant_id)):
    """Return distinct non-empty department values for the tenant."""
    cu.require("assets.view")
    from sqlalchemy import func as sqlfunc
    q = db.query(Employee.department).filter(Employee.department.isnot(None),
                                              Employee.department != "")
    if tenant_id is not None:
        q = q.filter(Employee.tenant_id == tenant_id)
    rows = q.distinct().order_by(Employee.department).all()
    return [r[0] for r in rows]

@router.post("")
def create(body: EmployeeIn, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
           tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("employees.manage")
    if tenant_id is None: raise HTTPException(400, "Specify a tenant")
    e = Employee(tenant_id=tenant_id, **body.model_dump())
    db.add(e); db.commit(); db.refresh(e)
    return _out(e)

@router.put("/{eid}")
def update(eid: int, body: EmployeeIn, db: Session = Depends(get_db),
           cu: CurrentUser = Depends(get_current_user),
           tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("employees.manage")
    e = db.query(Employee).get(eid)
    if not e or (tenant_id is not None and e.tenant_id != tenant_id):
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump().items(): setattr(e, k, v)
    db.commit(); db.refresh(e)
    return _out(e)

@router.delete("/{eid}")
def delete(eid: int, db: Session = Depends(get_db),
           cu: CurrentUser = Depends(get_current_user),
           tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("employees.manage")
    e = db.query(Employee).get(eid)
    if not e or (tenant_id is not None and e.tenant_id != tenant_id):
        raise HTTPException(404, "Not found")
    if e.assets: raise HTTPException(400, "Person still has assets assigned — use POST /{id}/reassign first")
    db.delete(e); db.commit()
    return {"ok": True}


class ReassignIn(BaseModel):
    to_employee_id: Optional[int] = None  # None = unassign


@router.post("/{eid}/reassign")
def bulk_reassign(
    eid: int,
    body: ReassignIn,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    """Reassign all assets from employee *eid* to *to_employee_id* (or unassign if None)."""
    cu.require("employees.manage")
    src = db.query(Employee).get(eid)
    if not src:
        raise HTTPException(404, "Employee not found")
    if tenant_id is not None and src.tenant_id != tenant_id:
        raise HTTPException(404, "Employee not found")

    dest: Optional[Employee] = None
    if body.to_employee_id is not None:
        dest = db.query(Employee).get(body.to_employee_id)
        if not dest:
            raise HTTPException(404, "Target employee not found")
        if tenant_id is not None and dest.tenant_id != tenant_id:
            raise HTTPException(404, "Target employee not found")

    moved = 0
    for asset in list(src.assets):
        asset.assigned_to_id = dest.id if dest else None
        if dest is None:
            asset.status = "available"
        moved += 1

    db.commit()
    return {"ok": True, "moved": moved, "to_employee_id": dest.id if dest else None}


@router.get("/{eid}/history")
def employee_history(
    eid: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    """Full assignment history for an employee — all assets ever checked out to them."""
    cu.require("assets.view")
    e = db.query(Employee).get(eid)
    if not e:
        raise HTTPException(404, "Employee not found")
    if tenant_id is not None and e.tenant_id != tenant_id:
        raise HTTPException(404, "Employee not found")

    rows = (
        db.query(CheckoutLog, Asset)
        .join(Asset, CheckoutLog.asset_id == Asset.id)
        .filter(CheckoutLog.employee_id == eid)
        .order_by(desc(CheckoutLog.timestamp))
        .all()
    )

    # Current assignments
    current_asset_ids = {a.id for a in e.assets}

    return {
        "employee": _out(e),
        "history": [
            {
                "id":            log_row.id,
                "asset_id":      asset.id,
                "asset_tag":     asset.asset_tag,
                "asset_name":    asset.name,
                "action":        log_row.action,
                "note":          log_row.note or "",
                "timestamp":     log_row.timestamp.isoformat() if log_row.timestamp else None,
                "currently_assigned": asset.id in current_asset_ids and asset.assigned_to_id == eid,
            }
            for log_row, asset in rows
        ],
    }
