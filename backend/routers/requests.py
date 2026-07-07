import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db.database import get_db
from models.models import AssetRequest, User, Tenant
from security import get_current_user, CurrentUser, get_tenant_id

log = logging.getLogger(__name__)
router = APIRouter()

APP_URL     = os.environ.get("APP_URL", "https://usetether.ca")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")

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
    cu.require("assets.view")
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

    # Notify MSP staff — non-blocking
    try:
        from email_service import send_request_notification
        tenant = db.query(Tenant).get(tenant_id)
        tenant_name = tenant.name if tenant else "Unknown"
        msp_staff = (
            db.query(User)
            .filter(User.is_msp_staff == True, User.active == True)
            .all()
        )
        view_url = f"{APP_URL}/#requests"
        for staff in msp_staff:
            if staff.email:
                send_request_notification(
                    to=staff.email,
                    name=staff.name,
                    tenant_name=tenant_name,
                    requester_name=cu.name,
                    title=body.title,
                    description=body.description or "",
                    priority=body.priority,
                    view_url=view_url,
                )
    except Exception as exc:
        log.warning(f"Request notification failed: {exc}")

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
    old_status = r.status
    r.status = body.status
    r.notes  = body.notes
    db.commit(); db.refresh(r)

    # Notify affected client users if status changed — non-blocking
    if body.status != old_status:
        try:
            from email_service import send_request_update
            tenant = db.query(Tenant).get(r.tenant_id)
            slug = tenant.slug if tenant else ""
            # Build tenant-specific URL: https://{slug}.{BASE_DOMAIN}/#requests
            if slug and BASE_DOMAIN and BASE_DOMAIN != "localhost":
                view_url = f"https://{slug}.{BASE_DOMAIN}/#requests"
            else:
                view_url = f"{APP_URL}/#requests"

            recipients: list[User] = []
            if r.requested_by_id:
                requester = db.query(User).get(r.requested_by_id)
                if requester and requester.email:
                    recipients.append(requester)

            # Also notify client_admin users in the same tenant
            admin_users = (
                db.query(User)
                .join(User.role)
                .filter(
                    User.tenant_id == r.tenant_id,
                    User.active == True,
                )
                .all()
            )
            seen_ids = {u.id for u in recipients}
            for u in admin_users:
                if u.id not in seen_ids and u.email:
                    role_name = u.role.name if u.role else ""
                    if role_name in ("client_admin", "client_manager"):
                        recipients.append(u)
                        seen_ids.add(u.id)

            for recipient in recipients:
                send_request_update(
                    to=recipient.email,
                    name=recipient.name,
                    title=r.title,
                    new_status=body.status,
                    notes=body.notes or "",
                    view_url=view_url,
                    tenant=tenant,
                )
        except Exception as exc:
            log.warning(f"Request update notification failed: {exc}")

    if body.status != old_status:
        try:
            from webhook_service import fire as _wh_fire
            tenant = db.query(Tenant).get(r.tenant_id)
            _wh_fire(tenant, "request.status_changed", {
                "request_id": r.id, "title": r.title,
                "old_status": old_status, "new_status": body.status,
            })
        except Exception:
            pass

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
