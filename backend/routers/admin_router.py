"""
routers/admin_router.py

Internal admin endpoints for MSP staff only.

  GET  /api/admin/status           — system info + config status
  POST /api/admin/backup/run       — trigger a backup immediately
  GET  /api/admin/backup/list      — list recent backups
  POST /api/admin/alerts/warranty  — trigger warranty alert emails now
"""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from models.models import Asset, User, Tenant, MspBilling
from security import get_current_user, CurrentUser

router = APIRouter()


@router.get("/status")
def system_status(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
):
    cu.require("msp.dashboard")

    from backup_service import BACKUP_ENABLED, _s3_configured, S3_BUCKET, S3_ENDPOINT
    from scheduler import WARRANTY_ALERT_ENABLED, WARRANTY_ALERT_DAYS
    from billing import is_saas

    total_assets  = db.query(Asset).count()
    total_tenants = db.query(Tenant).count()
    total_users   = db.query(User).filter(User.active == True).count()    # noqa: E712
    billing       = db.query(MspBilling).first()

    email_provider = os.environ.get("EMAIL_PROVIDER", "none")
    stripe_enabled = bool(os.environ.get("STRIPE_SECRET_KEY", ""))

    backup_dest = "Not configured"
    if BACKUP_ENABLED and _s3_configured():
        endpoint = S3_ENDPOINT or "AWS S3"
        backup_dest = f"{endpoint} → {S3_BUCKET}"

    return {
        "version":          "1.0.0",
        "deployment_mode":  os.environ.get("DEPLOYMENT_MODE", "selfhosted"),
        "saas_mode":        is_saas(),
        "timestamp":        datetime.utcnow().isoformat() + "Z",
        "database": {
            "total_assets":  total_assets,
            "total_tenants": total_tenants,
            "total_users":   total_users,
        },
        "billing": {
            "tier":          billing.tier if billing else "unknown",
            "interval":      billing.billing_interval if billing else "monthly",
            "stripe_active": bool(billing.stripe_subscription_id) if billing else False,
        } if billing else {},
        "services": {
            "email_provider":     email_provider,
            "email_configured":   email_provider != "none",
            "stripe_configured":  stripe_enabled,
            "backup_enabled":     BACKUP_ENABLED,
            "backup_configured":  BACKUP_ENABLED and _s3_configured(),
            "backup_destination": backup_dest,
            "warranty_alerts":    WARRANTY_ALERT_ENABLED,
            "warranty_window_days": WARRANTY_ALERT_DAYS,
        },
    }


@router.post("/backup/run")
def run_backup_now(
    db: Session = Depends(get_db),
    cu: CurrentUser = Depends(get_current_user),
):
    """Trigger an immediate backup. Runs synchronously — may take a few seconds."""
    cu.require("tenants.manage")

    from backup_service import run_backup, BACKUP_ENABLED, _s3_configured

    if not BACKUP_ENABLED:
        raise HTTPException(400,
            "Backups are not enabled. Set BACKUP_ENABLED=true in your .env")

    if not _s3_configured():
        raise HTTPException(400,
            "No S3 destination configured. Set BACKUP_S3_BUCKET, "
            "BACKUP_S3_ACCESS_KEY, and BACKUP_S3_SECRET_KEY in your .env")

    try:
        result = run_backup()
        return result
    except Exception as exc:
        raise HTTPException(500, f"Backup failed: {str(exc)}")


@router.get("/backup/list")
def list_backups(
    cu: CurrentUser = Depends(get_current_user),
):
    """List recent backup files from the configured S3 bucket."""
    cu.require("tenants.manage")

    from backup_service import list_backups as _list, BACKUP_ENABLED, _s3_configured

    if not BACKUP_ENABLED or not _s3_configured():
        return {"backups": [], "message": "Backup not configured"}

    return {"backups": _list(limit=20)}


@router.get("/backup/config")
def backup_config(
    cu: CurrentUser = Depends(get_current_user),
):
    """Return current backup configuration (no secrets)."""
    cu.require("tenants.manage")

    from backup_service import (BACKUP_ENABLED, BACKUP_INTERVAL_H,
                                BACKUP_RETAIN_DAYS, _s3_configured,
                                S3_BUCKET, S3_ENDPOINT, S3_REGION, S3_PREFIX)

    return {
        "enabled":          BACKUP_ENABLED,
        "configured":       _s3_configured(),
        "interval_hours":   BACKUP_INTERVAL_H,
        "retain_days":      BACKUP_RETAIN_DAYS,
        "bucket":           S3_BUCKET or "(not set)",
        "endpoint":         S3_ENDPOINT or "AWS S3 (default)",
        "region":           S3_REGION,
        "prefix":           S3_PREFIX,
        "access_key_set":   bool(os.environ.get("BACKUP_S3_ACCESS_KEY")),
    }


@router.post("/alerts/warranty")
def trigger_warranty_alerts(
    cu: CurrentUser = Depends(get_current_user),
):
    """Manually trigger warranty expiry emails right now."""
    cu.require("tenants.manage")

    from scheduler import run_warranty_alerts_now, WARRANTY_ALERT_ENABLED

    if not WARRANTY_ALERT_ENABLED:
        raise HTTPException(400,
            "Warranty alerts are disabled. Set WARRANTY_ALERTS_ENABLED=true in .env")

    email_provider = os.environ.get("EMAIL_PROVIDER", "none")
    if email_provider == "none":
        raise HTTPException(400,
            "Email is not configured. Set EMAIL_PROVIDER in .env to send alerts")

    try:
        result = run_warranty_alerts_now()
        return result
    except Exception as exc:
        raise HTTPException(500, f"Alert job failed: {str(exc)}")
