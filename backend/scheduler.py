"""
scheduler.py — Background task scheduler for Tether.

Runs two recurring jobs:
  1. Warranty expiry alerts — daily at 08:00 UTC
     Emails MSP admin(s) about assets with warranties expiring within 30 days.

  2. Automated backup — configurable interval (daily by default)
     Dumps the database and uploads to an S3-compatible bucket.

Neither job blocks the app startup. Both are optional — they only run
if the relevant configuration is present.

Usage: started via lifespan in main.py.
"""
import asyncio
import logging
import os
from datetime import datetime, date, timedelta

log = logging.getLogger(__name__)

# ── Warranty alert config ─────────────────────────────────────────────────────
WARRANTY_ALERT_DAYS    = int(os.environ.get("WARRANTY_ALERT_DAYS", "30"))
WARRANTY_ALERT_ENABLED = os.environ.get("WARRANTY_ALERTS_ENABLED", "true").lower() == "true"

# ── Backup config ─────────────────────────────────────────────────────────────
BACKUP_ENABLED  = os.environ.get("BACKUP_ENABLED", "false").lower() == "true"
BACKUP_INTERVAL = int(os.environ.get("BACKUP_INTERVAL_HOURS", "24"))


# ── Main scheduler loop ───────────────────────────────────────────────────────

async def start_scheduler():
    """Launch all background jobs. Called from app lifespan."""
    tasks = []
    if WARRANTY_ALERT_ENABLED:
        tasks.append(asyncio.create_task(_warranty_alert_loop()))
    if BACKUP_ENABLED:
        tasks.append(asyncio.create_task(_backup_loop()))

    if tasks:
        log.info(f"Scheduler started — {len(tasks)} job(s) active")
    return tasks


# ── Warranty expiry alerts ────────────────────────────────────────────────────

async def _warranty_alert_loop():
    """Run once daily at 08:00 UTC."""
    log.info("Warranty alert job: scheduled daily at 08:00 UTC")
    while True:
        now = datetime.utcnow()
        # Calculate seconds until next 08:00 UTC
        next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        wait = (next_run - now).total_seconds()
        log.debug(f"Warranty alert: next run in {wait/3600:.1f}h ({next_run.isoformat()}Z)")
        await asyncio.sleep(wait)
        try:
            await asyncio.get_event_loop().run_in_executor(None, _send_warranty_alerts)
        except Exception as exc:
            log.error(f"Warranty alert job failed: {exc}", exc_info=True)


def _send_warranty_alerts():
    """Find expiring warranties and email MSP admins."""
    from db.database import SessionLocal
    from models.models import Asset, Tenant, User, Role
    from email_service import send_warranty_alert
    import os

    db = SessionLocal()
    try:
        cutoff = date.today() + timedelta(days=WARRANTY_ALERT_DAYS)

        # Get all assets expiring within the window, grouped by tenant
        expiring = (
            db.query(Asset)
            .filter(Asset.warranty_expiry != None)          # noqa: E711
            .filter(Asset.warranty_expiry <= cutoff)
            .filter(Asset.warranty_expiry >= date.today())
            .order_by(Asset.warranty_expiry)
            .all()
        )

        if not expiring:
            log.info("Warranty alert: no assets expiring within window")
            return

        # Group by tenant
        by_tenant: dict = {}
        for asset in expiring:
            by_tenant.setdefault(asset.tenant_id, []).append(asset)

        # Get MSP admin users to notify
        msp_admin_role = db.query(Role).filter(Role.name == "msp_admin").first()
        if not msp_admin_role:
            return

        msp_admins = db.query(User).filter(
            User.is_msp_staff == True,          # noqa: E712
            User.role_id == msp_admin_role.id,
            User.active == True,                # noqa: E712
        ).all()

        if not msp_admins:
            log.warning("Warranty alert: no active MSP admins to notify")
            return

        app_url = os.environ.get("APP_URL", "https://usetether.ca")

        # Send one consolidated email per MSP admin covering all tenants
        total_assets = sum(len(v) for v in by_tenant.values())
        log.info(f"Warranty alert: {total_assets} assets expiring across "
                 f"{len(by_tenant)} tenant(s) — notifying {len(msp_admins)} admin(s)")

        all_expiring = [
            {
                "asset_tag":       a.asset_tag,
                "name":            a.name,
                "warranty_expiry": str(a.warranty_expiry),
                "tenant":          db.query(Tenant).get(a.tenant_id).name if a.tenant_id else "—",
            }
            for a in expiring
        ]

        for admin in msp_admins:
            try:
                send_warranty_alert(
                    to=admin.email,
                    name=admin.name or "MSP Admin",
                    tenant_name="All clients",
                    expiring=all_expiring,
                    login_url=app_url,
                )
                log.info(f"Warranty alert sent to {admin.email}")
            except Exception as exc:
                log.error(f"Failed to send warranty alert to {admin.email}: {exc}")

    finally:
        db.close()


# ── Manual trigger (for testing and the API endpoint) ─────────────────────────

def run_warranty_alerts_now() -> dict:
    """Synchronous wrapper — used by the API manual trigger."""
    from db.database import SessionLocal
    from models.models import Asset
    db = SessionLocal()
    try:
        cutoff = date.today() + timedelta(days=WARRANTY_ALERT_DAYS)
        count  = db.query(Asset).filter(
            Asset.warranty_expiry != None,         # noqa: E711
            Asset.warranty_expiry <= cutoff,
            Asset.warranty_expiry >= date.today(),
        ).count()
    finally:
        db.close()

    _send_warranty_alerts()
    return {"triggered": True, "assets_in_window": count}
