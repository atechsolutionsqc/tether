from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from models.models import Location
from schemas.schemas import LocationIn
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()

def _out(l): return {"id":l.id,"name":l.name,"address":l.address,"asset_count":len(l.assets)}

@router.get("")
def list_locations(db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
                   tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.view")
    q = db.query(Location)
    if tenant_id is not None: q = q.filter(Location.tenant_id == tenant_id)
    return [_out(l) for l in q.order_by(Location.name).all()]

@router.post("")
def create(body: LocationIn, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
           tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("locations.manage")
    if tenant_id is None: raise HTTPException(400, "Specify a tenant")
    if db.query(Location).filter(Location.tenant_id == tenant_id, Location.name == body.name).first():
        raise HTTPException(400, "Location already exists")
    l = Location(tenant_id=tenant_id, **body.model_dump())
    db.add(l); db.commit(); db.refresh(l)
    return _out(l)

@router.put("/{lid}")
def update(lid: int, body: LocationIn, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user)):
    cu.require("locations.manage")
    l = db.query(Location).get(lid)
    if not l: raise HTTPException(404, "Not found")
    l.name = body.name; l.address = body.address; db.commit(); db.refresh(l)
    return _out(l)

@router.delete("/{lid}")
def delete(lid: int, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user)):
    cu.require("locations.manage")
    l = db.query(Location).get(lid)
    if not l: raise HTTPException(404, "Not found")
    if l.assets: raise HTTPException(400, "Location still has assets")
    db.delete(l); db.commit()
    return {"ok": True}
