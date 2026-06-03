from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from models.models import User, Role, Permission, UserPermissionOverride
from schemas.schemas import UserIn, UserOut, UserPermOverride
from security import get_current_user, CurrentUser, hash_password

router = APIRouter()


def _out(u: User) -> dict:
    return {
        "id": u.id, "name": u.name, "email": u.email,
        "role_id": u.role_id,
        "role_name": u.role.name if u.role else None,
        "tenant_id": u.tenant_id,
        "tenant_name": u.tenant.name if u.tenant else None,
        "is_msp_staff": u.is_msp_staff,
        "active": u.active,
        "created_at": u.created_at,
    }


@router.get("")
def list_users(tenant_id: Optional[int] = None,
               db: Session = Depends(get_db),
               cu: CurrentUser = Depends(get_current_user)):
    if cu.is_msp_staff:
        cu.require("tenants.manage")
        q = db.query(User)
        if tenant_id:
            q = q.filter(User.tenant_id == tenant_id)
    else:
        cu.require("users.manage")
        q = db.query(User).filter(User.tenant_id == cu.tenant_id)
    return [_out(u) for u in q.order_by(User.name).all()]


@router.post("")
def create_user(body: UserIn, db: Session = Depends(get_db),
                cu: CurrentUser = Depends(get_current_user)):
    # MSP staff can create any user; client admins only within their tenant
    if cu.is_msp_staff:
        cu.require("tenants.manage")
    else:
        cu.require("users.manage")
        body.tenant_id = cu.tenant_id
        body.is_msp_staff = False

    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(400, "Email already in use")
    if not body.password:
        raise HTTPException(400, "Password is required")
    role = db.query(Role).get(body.role_id)
    if not role:
        raise HTTPException(400, "Role not found")

    u = User(
        name=body.name, email=body.email,
        password_hash=hash_password(body.password),
        role_id=body.role_id,
        tenant_id=body.tenant_id,
        is_msp_staff=body.is_msp_staff,
        active=body.active,
    )
    db.add(u); db.commit(); db.refresh(u)

    try:
        import os
        from email_service import send_welcome
        send_welcome(u.email, u.name or u.email,
                     os.environ.get("APP_URL", "https://usetether.ca"), role.name)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(f"Welcome email failed: {_e}")

    return _out(u)


@router.put("/{uid}")
def update_user(uid: int, body: UserIn, db: Session = Depends(get_db),
                cu: CurrentUser = Depends(get_current_user)):
    u = db.query(User).get(uid)
    if not u:
        raise HTTPException(404, "User not found")
    # permission check
    if cu.is_msp_staff:
        cu.require("tenants.manage")
    else:
        cu.require("users.manage")
        if u.tenant_id != cu.tenant_id:
            raise HTTPException(403, "Cannot edit user from another tenant")

    dup = db.query(User).filter(User.email == body.email, User.id != uid).first()
    if dup:
        raise HTTPException(400, "Email already in use")
    u.name = body.name; u.email = body.email
    u.role_id = body.role_id; u.active = body.active
    if body.password:
        u.password_hash = hash_password(body.password)
    if cu.is_msp_staff:
        u.tenant_id = body.tenant_id
        u.is_msp_staff = body.is_msp_staff
    db.commit(); db.refresh(u)
    return _out(u)


@router.delete("/{uid}")
def delete_user(uid: int, db: Session = Depends(get_db),
                cu: CurrentUser = Depends(get_current_user)):
    u = db.query(User).get(uid)
    if not u:
        raise HTTPException(404, "User not found")
    if cu.is_msp_staff:
        cu.require("tenants.manage")
    else:
        cu.require("users.manage")
        if u.tenant_id != cu.tenant_id:
            raise HTTPException(403, "Cannot delete user from another tenant")
    if u.id == cu.id:
        raise HTTPException(400, "Cannot delete your own account")
    db.delete(u); db.commit()
    return {"ok": True}


# ── Per-user permission overrides ─────────────────────────────────────────────

@router.get("/{uid}/permissions")
def get_permissions(uid: int, db: Session = Depends(get_db),
                    cu: CurrentUser = Depends(get_current_user)):
    u = db.query(User).get(uid)
    if not u:
        raise HTTPException(404, "User not found")
    role_perms = [rp.permission.key for rp in u.role.permissions] if u.role else []
    overrides = {ov.permission.key: ov.granted for ov in u.permission_overrides}
    effective = set(role_perms)
    for k, v in overrides.items():
        if v:
            effective.add(k)
        else:
            effective.discard(k)
    return {"role_permissions": role_perms, "overrides": overrides,
            "effective": sorted(effective)}


@router.put("/{uid}/permissions")
def set_permission_override(uid: int, body: UserPermOverride,
                             db: Session = Depends(get_db),
                             cu: CurrentUser = Depends(get_current_user)):
    if cu.is_msp_staff:
        cu.require("tenants.manage")
    else:
        cu.require("users.manage")
    u = db.query(User).get(uid)
    if not u:
        raise HTTPException(404, "User not found")
    perm = db.query(Permission).filter(Permission.key == body.permission_key).first()
    if not perm:
        raise HTTPException(404, "Permission not found")
    ov = db.query(UserPermissionOverride).filter_by(user_id=uid, permission_id=perm.id).first()
    if ov:
        ov.granted = body.granted
    else:
        db.add(UserPermissionOverride(user_id=uid, permission_id=perm.id, granted=body.granted))
    db.commit()
    return {"ok": True}


@router.delete("/{uid}/permissions/{pkey}")
def clear_permission_override(uid: int, pkey: str, db: Session = Depends(get_db),
                               cu: CurrentUser = Depends(get_current_user)):
    if cu.is_msp_staff:
        cu.require("tenants.manage")
    else:
        cu.require("users.manage")
    perm = db.query(Permission).filter(Permission.key == pkey).first()
    if not perm:
        raise HTTPException(404, "Permission not found")
    ov = db.query(UserPermissionOverride).filter_by(user_id=uid, permission_id=perm.id).first()
    if ov:
        db.delete(ov); db.commit()
    return {"ok": True}


# ── Roles ─────────────────────────────────────────────────────────────────────

@router.get("/roles/all")
def list_roles(db: Session = Depends(get_db),
               cu: CurrentUser = Depends(get_current_user)):
    roles = db.query(Role).order_by(Role.name).all()
    return [{
        "id": r.id, "name": r.name, "description": r.description,
        "is_msp_role": r.is_msp_role,
        "permissions": [rp.permission.key for rp in r.permissions],
    } for r in roles]
