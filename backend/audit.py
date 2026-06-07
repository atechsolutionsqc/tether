import logging
from typing import Optional
from sqlalchemy.orm import Session

_log = logging.getLogger("audit")


def log(
    db: Session,
    action: str,
    *,
    actor_id: Optional[int] = None,
    actor_email: str = "",
    actor_name: str = "",
    tenant_id: Optional[int] = None,
    tenant_name: str = "",
    resource: str = "",
    resource_id: str = "",
    detail: str = "",
    ip_address: str = "",
) -> None:
    """Write one audit log entry. Never raises — failures are swallowed."""
    try:
        from models.models import AuditLog
        entry = AuditLog(
            actor_id=actor_id,
            actor_email=actor_email,
            actor_name=actor_name,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            action=action,
            resource=resource,
            resource_id=str(resource_id),
            detail=detail,
            ip_address=ip_address,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        _log.error(f"Audit log write failed: {exc}")
