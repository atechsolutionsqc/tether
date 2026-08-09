import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from models.models import SavedFilter
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()


class SavedFilterIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    filters: dict = Field(default_factory=dict)


def _out(sf: SavedFilter) -> dict:
    try:
        fdata = json.loads(sf.filters or "{}")
    except Exception:
        fdata = {}
    return {
        "id":         sf.id,
        "name":       sf.name,
        "filters":    fdata,
        "created_at": sf.created_at.isoformat() if sf.created_at else None,
    }


@router.get("")
def list_saved_filters(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    rows = (
        db.query(SavedFilter)
        .filter(SavedFilter.user_id == cu.id, SavedFilter.tenant_id == tenant_id)
        .order_by(SavedFilter.name)
        .all()
    )
    return [_out(r) for r in rows]


@router.post("")
def create_saved_filter(
    body: SavedFilterIn,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    sf = SavedFilter(
        user_id=cu.id,
        tenant_id=tenant_id,
        name=body.name,
        filters=json.dumps(body.filters),
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)
    return _out(sf)


@router.delete("/{sfid}")
def delete_saved_filter(
    sfid: int,
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_tenant_id),
):
    sf = db.query(SavedFilter).get(sfid)
    if not sf or sf.user_id != cu.id or sf.tenant_id != tenant_id:
        raise HTTPException(404, "Saved filter not found")
    db.delete(sf)
    db.commit()
    return {"ok": True}
