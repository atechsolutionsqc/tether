from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from slugify import slugify

from db.database import get_db
from models.models import Tenant, TenantDomain, User, Role, Category, Location
from schemas.schemas import TenantIn, TenantOut
from security import get_current_user, CurrentUser, hash_password

router = APIRouter()


def _out(t: Tenant, db: Session) -> dict:
    return {
        "id": t.id, "name": t.name, "slug": t.slug,
        "logo_url": t.logo_url, "accent_color": t.accent_color,
        "currency": t.currency, "active": t.active,
        "created_at": t.created_at,
        "asset_count": len(t.assets),
        "user_count": len(t.users),
    }


@router.get("")
def list_tenants(db: Session = Depends(get_db),
                 cu: CurrentUser = Depends(get_current_user)):
    cu.require("tenants.manage")
    return [_out(t, db) for t in db.query(Tenant).order_by(Tenant.name).all()]


@router.post("")
def create_tenant(body: TenantIn, db: Session = Depends(get_db),
                  cu: CurrentUser = Depends(get_current_user)):
    cu.require("tenants.manage")
    slug = slugify(body.slug or body.name)
    if db.query(Tenant).filter(Tenant.slug == slug).first():
        raise HTTPException(400, "Slug already in use")
    t = Tenant(name=body.name, slug=slug, logo_url=body.logo_url,
               accent_color=body.accent_color, currency=body.currency)
    db.add(t)
    db.flush()
    # seed default categories + locations for new tenant
    for cname, icon in [("Laptop","laptop"),("Desktop","monitor"),("Monitor","tv"),
                         ("Phone","smartphone"),("Server","server"),
                         ("Network","wifi"),("Peripheral","mouse")]:
        db.add(Category(tenant_id=t.id, name=cname, icon=icon))
    for lname in ["Head Office", "Warehouse", "Remote"]:
        db.add(Location(tenant_id=t.id, name=lname))
    db.commit()
    db.refresh(t)
    return _out(t, db)


@router.get("/{tid}")
def get_tenant(tid: int, db: Session = Depends(get_db),
               cu: CurrentUser = Depends(get_current_user)):
    cu.require("tenants.manage")
    t = db.query(Tenant).get(tid)
    if not t:
        raise HTTPException(404, "Tenant not found")
    return _out(t, db)


@router.put("/{tid}")
def update_tenant(tid: int, body: TenantIn, db: Session = Depends(get_db),
                  cu: CurrentUser = Depends(get_current_user)):
    cu.require("tenants.manage")
    t = db.query(Tenant).get(tid)
    if not t:
        raise HTTPException(404, "Tenant not found")
    slug = slugify(body.slug or body.name)
    dup = db.query(Tenant).filter(Tenant.slug == slug, Tenant.id != tid).first()
    if dup:
        raise HTTPException(400, "Slug already in use")
    t.name = body.name; t.slug = slug; t.logo_url = body.logo_url
    t.accent_color = body.accent_color; t.currency = body.currency
    db.commit()
    db.refresh(t)
    return _out(t, db)


@router.delete("/{tid}")
def delete_tenant(tid: int, db: Session = Depends(get_db),
                  cu: CurrentUser = Depends(get_current_user)):
    cu.require("tenants.manage")
    t = db.query(Tenant).get(tid)
    if not t:
        raise HTTPException(404, "Tenant not found")
    db.delete(t); db.commit()
    return {"ok": True}


# ── Custom domains ────────────────────────────────────────────────────────────

@router.get("/{tid}/domains")
def list_domains(tid: int, db: Session = Depends(get_db),
                 cu: CurrentUser = Depends(get_current_user)):
    cu.require("tenants.manage")
    return db.query(TenantDomain).filter(TenantDomain.tenant_id == tid).all()


@router.post("/{tid}/domains")
def add_domain(tid: int, domain: str, db: Session = Depends(get_db),
               cu: CurrentUser = Depends(get_current_user)):
    cu.require("tenants.manage")
    if db.query(TenantDomain).filter(TenantDomain.domain == domain).first():
        raise HTTPException(400, "Domain already registered")
    d = TenantDomain(tenant_id=tid, domain=domain, verified=False)
    db.add(d); db.commit(); db.refresh(d)
    return d


@router.put("/{tid}/domains/{did}/verify")
def verify_domain(tid: int, did: int, db: Session = Depends(get_db),
                  cu: CurrentUser = Depends(get_current_user)):
    cu.require("tenants.manage")
    d = db.query(TenantDomain).get(did)
    if not d or d.tenant_id != tid:
        raise HTTPException(404, "Domain not found")
    d.verified = True; db.commit()
    return {"ok": True}


@router.delete("/{tid}/domains/{did}")
def delete_domain(tid: int, did: int, db: Session = Depends(get_db),
                  cu: CurrentUser = Depends(get_current_user)):
    cu.require("tenants.manage")
    d = db.query(TenantDomain).get(did)
    if not d or d.tenant_id != tid:
        raise HTTPException(404, "Domain not found")
    db.delete(d); db.commit()
    return {"ok": True}
