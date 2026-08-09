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

# ── Licence expiry alert config ────────────────────────────────────────────────
LICENCE_ALERT_ENABLED = os.environ.get("LICENCE_ALERTS_ENABLED", "true").lower() == "true"
LICENCE_ALERT_DAYS    = int(os.environ.get("LICENCE_ALERT_DAYS", "30"))

# ── Maintenance reminder config ────────────────────────────────────────────────
MAINTENANCE_ALERTS_ENABLED = os.environ.get("MAINTENANCE_ALERTS_ENABLED", "true").lower() == "true"
MAINTENANCE_ALERT_DAYS     = int(os.environ.get("MAINTENANCE_ALERT_DAYS", "3"))


# ── Main scheduler loop ───────────────────────────────────────────────────────

async def start_scheduler():
    """Launch all background jobs. Called from app lifespan."""
    tasks = []
    if WARRANTY_ALERT_ENABLED:
        tasks.append(asyncio.create_task(_warranty_alert_loop()))
    if LICENCE_ALERT_ENABLED:
        tasks.append(asyncio.create_task(_licence_alert_loop()))
    if BACKUP_ENABLED:
        tasks.append(asyncio.create_task(_backup_loop()))
    if MAINTENANCE_ALERTS_ENABLED:
        tasks.append(asyncio.create_task(_maintenance_alert_loop()))
    tasks.append(asyncio.create_task(_preview_user_cleanup_loop()))

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

        # Fire webhooks per tenant for warranty.expiring
        try:
            from webhook_service import fire as _wh_fire
            for t_id, assets in by_tenant.items():
                tenant = db.query(Tenant).get(t_id)
                if tenant and tenant.webhook_url:
                    _wh_fire(tenant, "warranty.expiring", {
                        "assets": [{"asset_tag": a.asset_tag, "name": a.name,
                                    "warranty_expiry": str(a.warranty_expiry)} for a in assets]
                    })
        except Exception as exc:
            log.warning(f"Warranty webhook failed: {exc}")

    finally:
        db.close()


# ── Licence expiry alerts ─────────────────────────────────────────────────────

async def _licence_alert_loop():
    """Run once daily at 09:00 UTC (offset from warranty alert to avoid overlap)."""
    log.info("Licence alert job: scheduled daily at 09:00 UTC")
    while True:
        now = datetime.utcnow()
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        wait = (next_run - now).total_seconds()
        log.debug(f"Licence alert: next run in {wait/3600:.1f}h ({next_run.isoformat()}Z)")
        await asyncio.sleep(wait)
        try:
            await asyncio.get_event_loop().run_in_executor(None, _send_licence_alerts)
        except Exception as exc:
            log.error(f"Licence alert job failed: {exc}", exc_info=True)


def _send_licence_alerts():
    from db.database import SessionLocal
    from models.models import SoftwareLicence, Tenant, User, Role
    from email_service import send_licence_expiry_alert
    import os

    db = SessionLocal()
    try:
        cutoff = date.today() + timedelta(days=LICENCE_ALERT_DAYS)
        expiring = (
            db.query(SoftwareLicence)
            .filter(SoftwareLicence.expiry_date != None)         # noqa: E711
            .filter(SoftwareLicence.expiry_date <= cutoff)
            .filter(SoftwareLicence.expiry_date >= date.today())
            .order_by(SoftwareLicence.expiry_date)
            .all()
        )

        if not expiring:
            log.info("Licence alert: no licences expiring within window")
            return

        msp_admin_role = db.query(Role).filter(Role.name == "msp_admin").first()
        if not msp_admin_role:
            return

        msp_admins = db.query(User).filter(
            User.is_msp_staff == True,         # noqa: E712
            User.role_id == msp_admin_role.id,
            User.active == True,               # noqa: E712
        ).all()

        if not msp_admins:
            log.warning("Licence alert: no active MSP admins to notify")
            return

        app_url = os.environ.get("APP_URL", "https://usetether.ca")

        all_expiring = []
        for lic in expiring:
            tenant = db.query(Tenant).get(lic.tenant_id)
            all_expiring.append({
                "name":        lic.name,
                "vendor":      lic.vendor or "—",
                "expiry_date": str(lic.expiry_date),
                "tenant":      tenant.name if tenant else "—",
            })

        log.info(f"Licence alert: {len(all_expiring)} licence(s) expiring — "
                 f"notifying {len(msp_admins)} admin(s)")

        for admin in msp_admins:
            try:
                send_licence_expiry_alert(
                    to=admin.email,
                    name=admin.name or "MSP Admin",
                    expiring=all_expiring,
                    login_url=app_url,
                )
                log.info(f"Licence alert sent to {admin.email}")
            except Exception as exc:
                log.error(f"Failed to send licence alert to {admin.email}: {exc}")
    finally:
        db.close()


def run_licence_alerts_now() -> dict:
    """Synchronous wrapper — used by the API manual trigger."""
    from db.database import SessionLocal
    from models.models import SoftwareLicence
    db = SessionLocal()
    try:
        cutoff = date.today() + timedelta(days=LICENCE_ALERT_DAYS)
        count  = db.query(SoftwareLicence).filter(
            SoftwareLicence.expiry_date != None,        # noqa: E711
            SoftwareLicence.expiry_date <= cutoff,
            SoftwareLicence.expiry_date >= date.today(),
        ).count()
    finally:
        db.close()

    _send_licence_alerts()
    return {"triggered": True, "licences_in_window": count}


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


# ── Maintenance reminders ─────────────────────────────────────────────────────

async def _maintenance_alert_loop():
    """Run once daily at 07:00 UTC."""
    log.info("Maintenance alert job: scheduled daily at 07:00 UTC")
    while True:
        now = datetime.utcnow()
        next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        wait = (next_run - now).total_seconds()
        log.debug(f"Maintenance alert: next run in {wait/3600:.1f}h")
        await asyncio.sleep(wait)
        try:
            _send_maintenance_alerts()
        except Exception as exc:
            log.error(f"Maintenance alert job failed: {exc}")


def _send_maintenance_alerts():
    """Email tenant admins about maintenance due within MAINTENANCE_ALERT_DAYS."""
    from db.database import SessionLocal
    from models.models import AssetMaintenance, User, Role
    from email_service import send_email

    db = SessionLocal()
    try:
        cutoff = date.today() + timedelta(days=MAINTENANCE_ALERT_DAYS)
        due = db.query(AssetMaintenance).filter(
            AssetMaintenance.status == "scheduled",
            AssetMaintenance.due_date <= cutoff,
            AssetMaintenance.due_date >= date.today(),
        ).all()

        by_tenant: dict = {}
        for m in due:
            by_tenant.setdefault(m.tenant_id, []).append(m)

        for tenant_id, items in by_tenant.items():
            admins = (
                db.query(User)
                .join(Role, User.role_id == Role.id)
                .filter(
                    User.tenant_id == tenant_id,
                    User.active == True,  # noqa: E712
                    Role.name.in_(["client_admin", "client_manager"]),
                )
                .all()
            )
            for admin in admins:
                rows_html = "".join(
                    f"<li><b>{m.title}</b> ({m.asset.asset_tag if m.asset else '?'}) — due {m.due_date}</li>"
                    for m in items
                )
                html = (
                    f"<p>Hi {admin.name},</p>"
                    f"<p>The following asset maintenance tasks are due within "
                    f"{MAINTENANCE_ALERT_DAYS} days:</p>"
                    f"<ul>{rows_html}</ul>"
                    f"<p>Log in to Tether to view details and mark them complete.</p>"
                )
                text = "\n".join(
                    f"  - {m.title} ({m.asset.asset_tag if m.asset else '?'}) — due {m.due_date}"
                    for m in items
                )
                try:
                    send_email(
                        to=admin.email,
                        subject=f"[Tether] {len(items)} maintenance task(s) coming up",
                        html=html,
                        text=text,
                    )
                    log.info(f"Maintenance alert sent to {admin.email}")
                except Exception as exc:
                    log.error(f"Failed to send maintenance alert to {admin.email}: {exc}")
    finally:
        db.close()


# ── Preview user cleanup ──────────────────────────────────────────────────────

async def _preview_user_cleanup_loop():
    """Delete stale __preview users daily at 03:00 UTC (older than 24h)."""
    while True:
        now = datetime.utcnow()
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            _cleanup_preview_users()
        except Exception as exc:
            log.error(f"Preview user cleanup failed: {exc}")


def _cleanup_preview_users():
    from db.database import SessionLocal
    from models.models import User
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        stale = db.query(User).filter(
            User.email.like("__preview@%"),
            User.created_at < cutoff,
        ).all()
        for u in stale:
            db.delete(u)
        if stale:
            db.commit()
            log.info(f"Cleaned up {len(stale)} stale preview user(s)")
    finally:
        db.close()
