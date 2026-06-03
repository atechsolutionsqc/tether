from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db.database import get_db
from models.models import AssetRequest
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()

PRIORITIES = ["low", "normal", "high", "urgent"]
STATUSES   = ["open", "in_progress", "fulfilled", "declined"]


class RequestIn(BaseModel):
    title: str
    description: str = ""
    priority: str = "normal"


class RequestUpdate(BaseModel):
    status: str
    notes: str = ""


def _out(r: AssetRequest) -> dict:
    return {
        "id": r.id, "tenant_id": r.tenant_id,
        "title": r.title, "description": r.description,
        "priority": r.priority, "status": r.status,
        "notes": r.notes, "requested_by_name": r.requested_by_name,
        "created_at": r.created_at, "updated_at": r.updated_at,
    }


@router.get("")
def list_requests(db: Session = Depends(get_db),
                  cu: CurrentUser = Depends(get_current_user),
                  tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.view")
    q = db.query(AssetRequest)
    if tenant_id is not None:
        q = q.filter(AssetRequest.tenant_id == tenant_id)
    return [_out(r) for r in q.order_by(AssetRequest.created_at.desc()).all()]


@router.post("")
def create_request(body: RequestIn, db: Session = Depends(get_db),
                   cu: CurrentUser = Depends(get_current_user),
                   tenant_id: Optional[int] = Depends(get_tenant_id)):
    if tenant_id is None:
        raise HTTPException(400, "Must be in a tenant context to submit a request")
    r = AssetRequest(
        tenant_id=tenant_id,
        requested_by_id=cu.id,
        requested_by_name=cu.name,
        title=body.title,
        description=body.description,
        priority=body.priority,
    )
    db.add(r); db.commit(); db.refresh(r)
    return _out(r)


@router.put("/{rid}")
def update_request(rid: int, body: RequestUpdate,
                   db: Session = Depends(get_db),
                   cu: CurrentUser = Depends(get_current_user),
                   tenant_id: Optional[int] = Depends(get_tenant_id)):
    r = db.query(AssetRequest).get(rid)
    if not r: raise HTTPException(404, "Request not found")
    if not cu.is_msp_staff:
        cu.require("assets.edit")
        if r.tenant_id != cu.tenant_id:
            raise HTTPException(403, "Not authorised")
    if body.status not in STATUSES:
        raise HTTPException(400, f"Status must be one of: {STATUSES}")
    r.status = body.status
    r.notes  = body.notes
    db.commit(); db.refresh(r)
    return _out(r)


@router.delete("/{rid}")
def delete_request(rid: int, db: Session = Depends(get_db),
                   cu: CurrentUser = Depends(get_current_user)):
    r = db.query(AssetRequest).get(rid)
    if not r: raise HTTPException(404, "Request not found")
    if not cu.is_msp_staff and r.tenant_id != cu.tenant_id:
        raise HTTPException(403, "Not authorised")
    db.delete(r); db.commit()
    return {"ok": True}
