"""
routers/custom_fields.py — Per-tenant custom field definitions and values.

Field defs are managed by MSP staff (requires categories.manage).
Field values are upserted per-asset (requires assets.edit).
"""
from typing import Optional, List
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from models.models import CustomFieldDef, CustomFieldValue, Asset
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()

_VALID_TYPES = {"text", "number", "date", "boolean", "url"}


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class FieldDefIn(BaseModel):
    label:      str  = Field(..., min_length=1, max_length=80)
    field_type: str  = Field("text", max_length=20)
    required:   bool = False


class FieldValueIn(BaseModel):
    field_def_id: int
    value:        str = Field("", max_length=2000)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_custom_field_values(asset_id: int, db: Session) -> list:
    """Return [{label, field_type, value}] for an asset."""
    rows = (
        db.query(CustomFieldValue, CustomFieldDef)
        .join(CustomFieldDef, CustomFieldValue.field_def_id == CustomFieldDef.id)
        .filter(CustomFieldValue.asset_id == asset_id)
        .all()
    )
    return [
        {
            "field_def_id": fv.field_def_id,
            "label":        fd.label,
            "field_type":   fd.field_type,
            "value":        fv.value,
        }
        for fv, fd in rows
    ]


def get_all_field_defs(tenant_id: int, db: Session) -> list:
    """Return all CustomFieldDef rows for a tenant, ordered by label."""
    defs = (
        db.query(CustomFieldDef)
        .filter(CustomFieldDef.tenant_id == tenant_id)
        .order_by(CustomFieldDef.label)
        .all()
    )
    return [
        {
            "id":         d.id,
            "label":      d.label,
            "field_type": d.field_type,
            "required":   d.required,
        }
        for d in defs
    ]


# ── Field definition CRUD (requires categories.manage) ───────────────────────

@router.get("/defs")
def list_field_defs(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("categories.manage")
    if tenant_id is None:
        raise HTTPException(400, "Specify a tenant")
    return get_all_field_defs(tenant_id, db)


@router.post("/defs")
def create_field_def(
    body: FieldDefIn,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("categories.manage")
    if tenant_id is None:
        raise HTTPException(400, "Specify a tenant")
    if body.field_type not in _VALID_TYPES:
        raise HTTPException(400, f"field_type must be one of: {', '.join(sorted(_VALID_TYPES))}")
    if db.query(CustomFieldDef).filter(
        CustomFieldDef.tenant_id == tenant_id,
        CustomFieldDef.label == body.label,
    ).first():
        raise HTTPException(400, "A custom field with that label already exists")
    d = CustomFieldDef(
        tenant_id=tenant_id,
        label=body.label,
        field_type=body.field_type,
        required=body.required,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "label": d.label, "field_type": d.field_type, "required": d.required}


@router.put("/defs/{def_id}")
def update_field_def(
    def_id: int,
    body: FieldDefIn,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("categories.manage")
    d = db.query(CustomFieldDef).filter(CustomFieldDef.id == def_id).first()
    if not d:
        raise HTTPException(404, "Custom field not found")
    if tenant_id is not None and d.tenant_id != tenant_id:
        raise HTTPException(404, "Custom field not found")
    if body.field_type not in _VALID_TYPES:
        raise HTTPException(400, f"field_type must be one of: {', '.join(sorted(_VALID_TYPES))}")
    dup = db.query(CustomFieldDef).filter(
        CustomFieldDef.tenant_id == d.tenant_id,
        CustomFieldDef.label == body.label,
        CustomFieldDef.id != def_id,
    ).first()
    if dup:
        raise HTTPException(400, "A custom field with that label already exists")
    d.label = body.label
    d.field_type = body.field_type
    d.required = body.required
    db.commit()
    return {"id": d.id, "label": d.label, "field_type": d.field_type, "required": d.required}


@router.delete("/defs/{def_id}")
def delete_field_def(
    def_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("categories.manage")
    d = db.query(CustomFieldDef).filter(CustomFieldDef.id == def_id).first()
    if not d:
        raise HTTPException(404, "Custom field not found")
    if tenant_id is not None and d.tenant_id != tenant_id:
        raise HTTPException(404, "Custom field not found")
    db.delete(d)
    db.commit()
    return {"ok": True}


# ── Field values (upsert per asset, requires assets.edit) ────────────────────

@router.get("/values/{asset_id}")
def get_values(
    asset_id: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.view")
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    if tenant_id is not None and a.tenant_id != tenant_id:
        raise HTTPException(404, "Asset not found")
    return get_custom_field_values(asset_id, db)


@router.put("/values/{asset_id}")
def upsert_values(
    asset_id: int,
    body: List[FieldValueIn] = Body(...),
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    cu.require("assets.edit")
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    if tenant_id is not None and a.tenant_id != tenant_id:
        raise HTTPException(404, "Asset not found")

    for item in body:
        # Verify the field def belongs to this tenant
        fd = db.query(CustomFieldDef).filter(CustomFieldDef.id == item.field_def_id).first()
        if not fd or (tenant_id is not None and fd.tenant_id != tenant_id):
            continue
        existing = db.query(CustomFieldValue).filter(
            CustomFieldValue.field_def_id == item.field_def_id,
            CustomFieldValue.asset_id == asset_id,
        ).first()
        if existing:
            existing.value = item.value
        else:
            db.add(CustomFieldValue(
                field_def_id=item.field_def_id,
                asset_id=asset_id,
                value=item.value,
            ))
    db.commit()
    return get_custom_field_values(asset_id, db)
