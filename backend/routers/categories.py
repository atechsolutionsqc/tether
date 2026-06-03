from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from models.models import Category
from schemas.schemas import CategoryIn
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()

def _out(c): return {"id":c.id,"name":c.name,"icon":c.icon,"asset_count":len(c.assets)}

@router.get("")
def list_categories(db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
                    tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.view")
    q = db.query(Category)
    if tenant_id is not None: q = q.filter(Category.tenant_id == tenant_id)
    return [_out(c) for c in q.order_by(Category.name).all()]

@router.post("")
def create(body: CategoryIn, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
           tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("categories.manage")
    if tenant_id is None: raise HTTPException(400, "Specify a tenant")
    if db.query(Category).filter(Category.tenant_id == tenant_id, Category.name == body.name).first():
        raise HTTPException(400, "Category already exists")
    c = Category(tenant_id=tenant_id, **body.model_dump())
    db.add(c); db.commit(); db.refresh(c)
    return _out(c)

@router.put("/{cid}")
def update(cid: int, body: CategoryIn, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
           tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("categories.manage")
    q = db.query(Category).filter(Category.id == cid)
    if tenant_id is not None:
        q = q.filter(Category.tenant_id == tenant_id)
    c = q.first()
    if not c: raise HTTPException(404, "Not found")
    c.name = body.name; c.icon = body.icon; db.commit(); db.refresh(c)
    return _out(c)

@router.delete("/{cid}")
def delete(cid: int, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
           tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("categories.manage")
    q = db.query(Category).filter(Category.id == cid)
    if tenant_id is not None:
        q = q.filter(Category.tenant_id == tenant_id)
    c = q.first()
    if not c: raise HTTPException(404, "Not found")
    if c.assets: raise HTTPException(400, "Category still has assets")
    db.delete(c); db.commit()
    return {"ok": True}
