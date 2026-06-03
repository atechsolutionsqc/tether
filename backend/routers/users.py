from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from models.models import Employee
from schemas.schemas import EmployeeIn
from security import get_current_user, CurrentUser, get_tenant_id

router = APIRouter()

def _out(e): return {"id":e.id,"name":e.name,"email":e.email,"department":e.department,"asset_count":len(e.assets)}

@router.get("")
def list_employees(db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
                   tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("assets.view")
    q = db.query(Employee)
    if tenant_id is not None: q = q.filter(Employee.tenant_id == tenant_id)
    return [_out(e) for e in q.order_by(Employee.name).all()]

@router.post("")
def create(body: EmployeeIn, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user),
           tenant_id: Optional[int] = Depends(get_tenant_id)):
    cu.require("employees.manage")
    if tenant_id is None: raise HTTPException(400, "Specify a tenant")
    e = Employee(tenant_id=tenant_id, **body.model_dump())
    db.add(e); db.commit(); db.refresh(e)
    return _out(e)

@router.put("/{eid}")
def update(eid: int, body: EmployeeIn, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user)):
    cu.require("employees.manage")
    e = db.query(Employee).get(eid)
    if not e: raise HTTPException(404, "Not found")
    for k, v in body.model_dump().items(): setattr(e, k, v)
    db.commit(); db.refresh(e)
    return _out(e)

@router.delete("/{eid}")
def delete(eid: int, db: Session = Depends(get_db), cu: CurrentUser = Depends(get_current_user)):
    cu.require("employees.manage")
    e = db.query(Employee).get(eid)
    if not e: raise HTTPException(404, "Not found")
    if e.assets: raise HTTPException(400, "Person still has assets assigned")
    db.delete(e); db.commit()
    return {"ok": True}
