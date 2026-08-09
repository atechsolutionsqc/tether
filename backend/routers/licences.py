"""
routers/licences.py — Software licence management.

All read endpoints require assets.view.
All write endpoints require assets.create.
All scoped to the current tenant via host-header resolution.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import audit
from db.database import get_db
from models.models import (
    SoftwareLicence, LicenceAssignment, Employee, Asset, Tenant,
)
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()


# ── Pydantic bodies ───────────────────────────────────────────────────────────

class LicenceIn(BaseModel):
    name:          str
    vendor:        str = ""
    licence_type:  str = ""
    total_seats:   Optional[int] = None
    purchase_date: Optional[date] = None
    expiry_date:   Optional[date] = None
    purchase_cost: Optional[float] = None
    renewal_cost:  Optional[float] = None
    licence_key:   str = ""
    notes:         str = ""


class AssignIn(BaseModel):
    employee_id: Optional[int] = None
    asset_id:    Optional[int] = None
    notes:       str = ""


# ── Serialisation helper ──────────────────────────────────────────────────────

def _out(lic: SoftwareLicence, include_assignments: bool = False) -> dict:
    seats_used = len(lic.assignments)
    seats_available = (
        None if lic.total_seats is None
        else max(0, lic.total_seats - seats_used)
    )
    d = {
        "id":             lic.id,
        "tenant_id":      lic.tenant_id,
        "name":           lic.name,
        "vendor":         lic.vendor,
        "licence_type":   lic.licence_type,
        "total_seats":    lic.total_seats,
        "seats_used":     seats_used,
        "seats_available": seats_available,
        "purchase_date":  lic.purchase_date.isoformat() if lic.purchase_date else None,
        "expiry_date":    lic.expiry_date.isoformat() if lic.expiry_date else None,
        "purchase_cost":  lic.purchase_cost,
        "renewal_cost":   lic.renewal_cost,
        "licence_key":    lic.licence_key,
        "notes":          lic.notes,
        "created_at":     lic.created_at.isoformat() if lic.created_at else None,
        "updated_at":     lic.updated_at.isoformat() if lic.updated_at else None,
    }
    if include_assignments:
        d["assignments"] = [
            {
                "id":            a.id,
                "employee_id":   a.employee_id,
                "employee_name": a.employee.name if a.employee else None,
                "asset_id":      a.asset_id,
                "asset_tag":     a.asset.asset_tag if a.asset else None,
                "assigned_at":   a.assigned_at.isoformat() if a.assigned_at else None,
                "notes":         a.notes,
            }
            for a in lic.assignments
        ]
    return d


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("")
def list_licences(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.view")
    q = db.query(SoftwareLicence)
    if tenant_id is not None:
        q = q.filter(SoftwareLicence.tenant_id == tenant_id)
    return [_out(lic) for lic in q.order_by(SoftwareLicence.name).all()]


# ── Expiring ──────────────────────────────────────────────────────────────────

@router.get("/expiring")
def expiring_licences(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.view")
    cutoff = date.today() + timedelta(days=days)
    today  = date.today()
    q = db.query(SoftwareLicence).filter(
        SoftwareLicence.expiry_date.isnot(None),
        SoftwareLicence.expiry_date >= today,
        SoftwareLicence.expiry_date <= cutoff,
    )
    if tenant_id is not None:
        q = q.filter(SoftwareLicence.tenant_id == tenant_id)
    return [_out(lic) for lic in q.order_by(SoftwareLicence.expiry_date).all()]


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("")
def create_licence(
    body: LicenceIn,
    request: Request,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.create")
    if tenant_id is None:
        raise HTTPException(400, "Specify a tenant")
    lic = SoftwareLicence(
        tenant_id=tenant_id, name=body.name, vendor=body.vendor,
        licence_type=body.licence_type, total_seats=body.total_seats,
        purchase_date=body.purchase_date, expiry_date=body.expiry_date,
        purchase_cost=body.purchase_cost, renewal_cost=body.renewal_cost,
        licence_key=body.licence_key, notes=body.notes,
    )
    db.add(lic); db.commit(); db.refresh(lic)
    audit.log(db, "licence.create", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tenant_id, resource="licence",
              resource_id=str(lic.id), detail=f"Created licence {lic.name}",
              ip_address=request.client.host if request.client else "")
    return _out(lic)


# ── Get one ───────────────────────────────────────────────────────────────────

@router.get("/{lid}")
def get_licence(
    lid: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.view")
    lic = _get_scoped(lid, tenant_id, db)
    return _out(lic, include_assignments=True)


# ── Update ────────────────────────────────────────────────────────────────────

@router.put("/{lid}")
def update_licence(
    lid: int,
    body: LicenceIn,
    request: Request,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.create")
    lic = _get_scoped(lid, tenant_id, db)
    for field, val in body.model_dump().items():
        setattr(lic, field, val)
    db.commit(); db.refresh(lic)
    audit.log(db, "licence.update", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=lic.tenant_id, resource="licence",
              resource_id=str(lic.id), detail=f"Updated licence {lic.name}",
              ip_address=request.client.host if request.client else "")
    return _out(lic)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{lid}")
def delete_licence(
    lid: int,
    request: Request,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.create")
    lic = _get_scoped(lid, tenant_id, db)
    name, tid = lic.name, lic.tenant_id
    db.delete(lic); db.commit()
    audit.log(db, "licence.delete", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=tid, resource="licence",
              resource_id=str(lid), detail=f"Deleted licence {name}",
              ip_address=request.client.host if request.client else "")
    return {"ok": True}


# ── Assign ────────────────────────────────────────────────────────────────────

@router.post("/{lid}/assign")
def assign_seat(
    lid: int,
    body: AssignIn,
    request: Request,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.create")
    lic = _get_scoped(lid, tenant_id, db)

    if lic.total_seats is not None and len(lic.assignments) >= lic.total_seats:
        raise HTTPException(400, "No seats available")

    if body.employee_id:
        emp = db.query(Employee).get(body.employee_id)
        if emp is None or (tenant_id is not None and emp.tenant_id != tenant_id):
            raise HTTPException(400, "Employee not found in this tenant")

    if body.asset_id:
        asset = db.query(Asset).get(body.asset_id)
        if asset is None or (tenant_id is not None and asset.tenant_id != tenant_id):
            raise HTTPException(400, "Asset not found in this tenant")

    assignment = LicenceAssignment(
        licence_id=lid,
        employee_id=body.employee_id,
        asset_id=body.asset_id,
        notes=body.notes,
    )
    db.add(assignment); db.commit(); db.refresh(assignment)
    audit.log(db, "licence.assign", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=lic.tenant_id, resource="licence",
              resource_id=str(lid), detail=f"Assigned seat on {lic.name}",
              ip_address=request.client.host if request.client else "")
    return {
        "id":            assignment.id,
        "licence_id":    assignment.licence_id,
        "employee_id":   assignment.employee_id,
        "employee_name": assignment.employee.name if assignment.employee else None,
        "asset_id":      assignment.asset_id,
        "asset_tag":     assignment.asset.asset_tag if assignment.asset else None,
        "assigned_at":   assignment.assigned_at.isoformat(),
        "notes":         assignment.notes,
    }


# ── Unassign ──────────────────────────────────────────────────────────────────

@router.delete("/{lid}/assign/{aid}")
def unassign_seat(
    lid: int,
    aid: int,
    request: Request,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.create")
    lic = _get_scoped(lid, tenant_id, db)
    assignment = db.query(LicenceAssignment).filter(
        LicenceAssignment.id == aid,
        LicenceAssignment.licence_id == lid,
    ).first()
    if not assignment:
        raise HTTPException(404, "Assignment not found")
    db.delete(assignment); db.commit()
    audit.log(db, "licence.unassign", actor_id=cu.id, actor_email=cu.email,
              actor_name=cu.name, tenant_id=lic.tenant_id, resource="licence",
              resource_id=str(lid), detail=f"Unassigned seat on {lic.name}",
              ip_address=request.client.host if request.client else "")
    return {"ok": True}


# ── Internal helper ───────────────────────────────────────────────────────────

def _get_scoped(lid: int, tenant_id: Optional[int], db: Session) -> SoftwareLicence:
    lic = db.query(SoftwareLicence).get(lid)
    if lic is None or (tenant_id is not None and lic.tenant_id != tenant_id):
        raise HTTPException(404, "Licence not found")
    return lic
