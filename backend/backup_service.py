"""
backup_service.py — Automated database backup for Tether.

Supports any S3-compatible storage provider:
  - AWS S3
  - Backblaze B2 (S3-compatible API)
  - Cloudflare R2
  - MinIO (self-hosted)
  - DigitalOcean Spaces
  - Wasabi
  - Any other S3-compatible service

Configuration (.env):
  BACKUP_ENABLED=true              # master switch (default: false)
  BACKUP_INTERVAL_HOURS=24         # how often to run (default: 24)
  BACKUP_RETAIN_DAYS=30            # delete backups older than N days (default: 30)

  # S3-compatible credentials
  BACKUP_S3_ENDPOINT=              # leave blank for AWS S3; set for B2/R2/etc.
  BACKUP_S3_BUCKET=tether-backups
  BACKUP_S3_ACCESS_KEY=your-key
  BACKUP_S3_SECRET_KEY=your-secret
  BACKUP_S3_REGION=us-east-1       # required for AWS; varies by provider
  BACKUP_S3_PREFIX=backups/        # optional path prefix inside the bucket

Provider-specific endpoint examples:
  Backblaze B2:  https://s3.us-west-004.backblazeb2.com
  Cloudflare R2: https://<account-id>.r2.cloudflarestorage.com
  DigitalOcean:  https://nyc3.digitaloceanspaces.com
  MinIO:         http://localhost:9000
  AWS S3:        (leave BACKUP_S3_ENDPOINT blank)

The backup file is a SQL dump for MariaDB/MySQL/PostgreSQL,
or a copy of the SQLite file.
"""
import asyncio
import gzip
import io
import logging
import os
import subprocess
import shutil
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BACKUP_ENABLED       = os.environ.get("BACKUP_ENABLED", "false").lower() == "true"
BACKUP_INTERVAL_H    = int(os.environ.get("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_RETAIN_DAYS   = int(os.environ.get("BACKUP_RETAIN_DAYS", "30"))

S3_ENDPOINT          = os.environ.get("BACKUP_S3_ENDPOINT", "")         # blank = AWS S3
S3_BUCKET            = os.environ.get("BACKUP_S3_BUCKET", "")
S3_ACCESS_KEY        = os.environ.get("BACKUP_S3_ACCESS_KEY", "")
S3_SECRET_KEY        = os.environ.get("BACKUP_S3_SECRET_KEY", "")
S3_REGION            = os.environ.get("BACKUP_S3_REGION", "us-east-1")
S3_PREFIX            = os.environ.get("BACKUP_S3_PREFIX", "backups/")


def _s3_configured() -> bool:
    return bool(S3_BUCKET and S3_ACCESS_KEY and S3_SECRET_KEY)


def _get_s3_client():
    import boto3
    kwargs = {
        "aws_access_key_id":     S3_ACCESS_KEY,
        "aws_secret_access_key": S3_SECRET_KEY,
        "region_name":           S3_REGION,
    }
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
    return boto3.client("s3", **kwargs)


# ── Backup loop (called from scheduler) ──────────────────────────────────────

async def backup_loop():
    log.info(f"Backup job: running every {BACKUP_INTERVAL_H}h")
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_H * 3600)
        try:
            result = await asyncio.get_event_loop().run_in_executor(None, run_backup)
            log.info(f"Scheduled backup complete: {result}")
        except Exception as exc:
            log.error(f"Backup job failed: {exc}", exc_info=True)


# ── Core backup logic ─────────────────────────────────────────────────────────

def run_backup() -> dict:
    """
    Perform a backup right now. Returns a dict with status info.
    Raises on fatal errors.
    """
    if not BACKUP_ENABLED:
        return {"status": "disabled", "message": "BACKUP_ENABLED is not true"}

    if not _s3_configured():
        return {"status": "no_destination",
                "message": "No S3 bucket configured. Set BACKUP_S3_BUCKET, "
                           "BACKUP_S3_ACCESS_KEY, BACKUP_S3_SECRET_KEY in .env"}

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    db_url    = os.environ.get("DATABASE_URL", "")
    db_host   = os.environ.get("DB_HOST", "")

    # Determine backup method
    if db_url.startswith("postgresql") or db_url.startswith("postgres"):
        data, filename = _backup_postgres(db_url, timestamp)
    elif db_url.startswith("mysql") or db_host:
        data, filename = _backup_mariadb(db_url, db_host, timestamp)
    else:
        data, filename = _backup_sqlite(timestamp)

    # Compress
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(data)
    compressed = buf.getvalue()
    filename  += ".gz"

    # Upload
    key = f"{S3_PREFIX.rstrip('/')}/{filename}".lstrip("/")
    s3  = _get_s3_client()
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=compressed,
        ContentType="application/gzip",
        Metadata={
            "tether-backup-timestamp": timestamp,
            "tether-version":          "1.0",
        },
    )

    size_kb = len(compressed) // 1024
    log.info(f"Backup uploaded: s3://{S3_BUCKET}/{key} ({size_kb} KB)")

    # Prune old backups
    pruned = _prune_old_backups(s3, S3_PREFIX)

    return {
        "status":      "ok",
        "file":        key,
        "size_kb":     size_kb,
        "timestamp":   timestamp,
        "pruned":      pruned,
        "destination": f"s3://{S3_BUCKET}/{key}",
    }


# ── Database dump functions ───────────────────────────────────────────────────

def _backup_mariadb(db_url: str, db_host: str, timestamp: str):
    """Dump MariaDB/MySQL via mysqldump or from DATABASE_URL."""
    if db_url.startswith("mysql"):
        # Parse from URL: mysql+pymysql://user:pass@host:port/db
        import urllib.parse
        url = db_url.replace("mysql+pymysql://", "mysql://")
        p   = urllib.parse.urlparse(url)
        host, port, user, pw, db = (
            p.hostname, p.port or 3306, p.username, p.password,
            p.path.lstrip("/"),
        )
    else:
        host = db_host
        port = int(os.environ.get("DB_PORT", "3306"))
        user = os.environ.get("DB_USER", "tether")
        pw   = os.environ.get("DB_PASSWORD", "")
        db   = os.environ.get("DB_NAME", "tether")

    cmd = [
        "mysqldump",
        f"--host={host}", f"--port={port}",
        f"--user={user}", f"--password={pw}",
        "--single-transaction", "--routines", "--triggers",
        "--set-gtid-purged=OFF",
        db,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"mysqldump failed: {result.stderr.decode()[:200]}")

    return result.stdout, f"tether-{timestamp}.sql"


def _backup_postgres(db_url: str, timestamp: str):
    """Dump PostgreSQL via pg_dump."""
    cmd = ["pg_dump", "--format=plain", "--no-password", db_url]
    result = subprocess.run(cmd, capture_output=True, timeout=300,
                            env={**os.environ, "PGPASSWORD": ""})
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.decode()[:200]}")
    return result.stdout, f"tether-{timestamp}.sql"


def _backup_sqlite(timestamp: str):
    """Copy the SQLite file."""
    data_dir  = os.environ.get("TETHER_DATA", "./data")
    db_path   = Path(data_dir) / "tether.db"
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found at {db_path}")
    return db_path.read_bytes(), f"tether-{timestamp}.db"


# ── Prune old backups ─────────────────────────────────────────────────────────

def _prune_old_backups(s3, prefix: str) -> int:
    """Delete backups older than BACKUP_RETAIN_DAYS. Returns count deleted."""
    if BACKUP_RETAIN_DAYS <= 0:
        return 0

    cutoff = datetime.utcnow() - timedelta(days=BACKUP_RETAIN_DAYS)
    paginator = s3.get_paginator("list_objects_v2")
    deleted   = 0

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix.lstrip("/")):
        for obj in page.get("Contents", []):
            if obj["LastModified"].replace(tzinfo=None) < cutoff:
                s3.delete_object(Bucket=S3_BUCKET, Key=obj["Key"])
                deleted += 1
                log.debug(f"Pruned old backup: {obj['Key']}")

    if deleted:
        log.info(f"Pruned {deleted} backup(s) older than {BACKUP_RETAIN_DAYS} days")
    return deleted


# ── List recent backups ───────────────────────────────────────────────────────

def list_backups(limit: int = 20) -> list:
    """List recent backup files from S3."""
    if not _s3_configured():
        return []
    try:
        s3       = _get_s3_client()
        prefix   = S3_PREFIX.lstrip("/")
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix,
                                      MaxKeys=limit)
        objects  = response.get("Contents", [])
        objects.sort(key=lambda o: o["LastModified"], reverse=True)
        return [
            {
                "key":          o["Key"],
                "size_kb":      o["Size"] // 1024,
                "last_modified": o["LastModified"].strftime("%Y-%m-%d %H:%M UTC"),
            }
            for o in objects[:limit]
        ]
    except Exception as exc:
        log.warning(f"Could not list backups: {exc}")
        return []
