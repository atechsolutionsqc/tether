import os
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db.database import get_db
from models.models import InviteToken, User, Role, Tenant
from security import get_current_user, CurrentUser, hash_password, resolve_tenant_slug

router = APIRouter()


class InviteCreate(BaseModel):
    email: str
    name: str = ""
    role_id: int
    tenant_id: int
    expires_hours: int = 72


class AcceptInvite(BaseModel):
    token: str
    name: str
    password: str


@router.post("")
def create_invite(body: InviteCreate, db: Session = Depends(get_db),
                  cu: CurrentUser = Depends(get_current_user)):
    # MSP can invite to any tenant; client admins only their own
    if cu.is_msp_staff:
        cu.require("tenants.manage")
    else:
        cu.require("users.manage")
        if body.tenant_id != cu.tenant_id:
            raise HTTPException(403, "Cannot invite to another tenant")

    tenant = db.query(Tenant).get(body.tenant_id)
    if not tenant: raise HTTPException(404, "Tenant not found")
    role = db.query(Role).get(body.role_id)
    if not role: raise HTTPException(404, "Role not found")

    # invalidate any existing unused invite for this email+tenant
    db.query(InviteToken).filter(
        InviteToken.email == body.email,
        InviteToken.tenant_id == body.tenant_id,
        InviteToken.used == False
    ).delete()

    token = secrets.token_urlsafe(32)
    inv = InviteToken(
        token=token,
        tenant_id=body.tenant_id,
        role_id=body.role_id,
        email=body.email,
        name=body.name,
        expires_at=datetime.utcnow() + timedelta(hours=body.expires_hours),
    )
    db.add(inv); db.commit()

    invite_url = f"{os.environ.get('APP_URL', 'https://usetether.ca')}/invite/{token}"

    # Send invite email (non-blocking — failure doesn't abort the request)
    try:
        from email_service import send_invite
        send_invite(
            to=body.email,
            name=body.name or body.email.split("@")[0],
            invite_url=invite_url,
            tenant_name=tenant.name,
            role=role.name,
        )
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(f"Invite email failed to {body.email}: {_e}")

    return {
        "token":      token,
        "invite_url": invite_url,
        "email":      body.email,
        "tenant":     tenant.name,
        "expires_at": inv.expires_at.isoformat(),
    }


@router.get("/validate/{token}")
def validate_invite(token: str, db: Session = Depends(get_db)):
    inv = db.query(InviteToken).filter(InviteToken.token == token).first()
    if not inv or inv.used:
        raise HTTPException(400, "Invite link is invalid or has already been used")
    if datetime.utcnow() > inv.expires_at:
        raise HTTPException(400, "Invite link has expired")
    return {
        "email": inv.email,
        "name": inv.name,
        "tenant_name": inv.tenant.name,
        "tenant_slug": inv.tenant.slug,
        "tenant_accent": inv.tenant.accent_color,
        "tenant_logo":   inv.tenant.logo_url,
        "role_name": inv.role.description or inv.role.name,
    }


@router.post("/accept")
def accept_invite(body: AcceptInvite, db: Session = Depends(get_db)):
    inv = db.query(InviteToken).filter(InviteToken.token == body.token).first()
    if not inv or inv.used:
        raise HTTPException(400, "Invite is invalid or already used")
    if datetime.utcnow() > inv.expires_at:
        raise HTTPException(400, "Invite has expired")
    if db.query(User).filter(User.email == inv.email).first():
        raise HTTPException(400, "An account with this email already exists")

    user = User(
        tenant_id=inv.tenant_id,
        role_id=inv.role_id,
        name=body.name or inv.name or inv.email.split("@")[0],
        email=inv.email,
        password_hash=hash_password(body.password),
        is_msp_staff=False,
        active=True,
    )
    db.add(user)
    inv.used = True
    db.commit()
    return {"ok": True, "email": inv.email, "tenant_slug": inv.tenant.slug}


@router.get("")
def list_invites(db: Session = Depends(get_db),
                 cu: CurrentUser = Depends(get_current_user)):
    if cu.is_msp_staff:
        cu.require("tenants.manage")
        invites = db.query(InviteToken).order_by(InviteToken.created_at.desc()).all()
    else:
        cu.require("users.manage")
        invites = db.query(InviteToken).filter(
            InviteToken.tenant_id == cu.tenant_id
        ).order_by(InviteToken.created_at.desc()).all()
    return [{
        "id": i.id, "email": i.email, "name": i.name,
        "tenant_name": i.tenant.name, "role_name": i.role.name,
        "used": i.used, "expires_at": i.expires_at, "created_at": i.created_at,
    } for i in invites]


@router.delete("/{invite_id}")
def revoke_invite(invite_id: int, db: Session = Depends(get_db),
                  cu: CurrentUser = Depends(get_current_user)):
    inv = db.query(InviteToken).get(invite_id)
    if not inv: raise HTTPException(404, "Invite not found")
    db.delete(inv); db.commit()
    return {"ok": True}
