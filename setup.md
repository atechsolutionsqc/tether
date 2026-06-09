# Tether Setup Guide

This guide covers every supported installation method from a five-minute local trial to a production MSP deployment.

---

## Table of Contents

1. [Choose your deployment mode](#1-choose-your-deployment-mode)
2. [Prerequisites](#2-prerequisites)
3. [Docker (recommended)](#3-docker-recommended)
   - [Standalone — single company](#standalone--single-company)
   - [MSP — multiple clients](#msp--multiple-clients)
4. [Bare-metal (Linux)](#4-bare-metal-linux)
5. [DNS setup](#5-dns-setup)
6. [Reverse proxy (HTTPS)](#6-reverse-proxy-https)
   - [Caddy](#caddy)
   - [Nginx](#nginx)
7. [Environment variable reference](#7-environment-variable-reference)
8. [Database backends](#8-database-backends)
9. [Email setup](#9-email-setup)
10. [Automated backups](#10-automated-backups)
11. [First login and initial configuration](#11-first-login-and-initial-configuration)
12. [Updating](#12-updating)
13. [Backup and restore](#13-backup-and-restore)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Choose your deployment mode

Set `DEPLOYMENT_MODE` in your `.env` file.

| Mode | Use case | Subdomain DNS needed? |
|------|----------|-----------------------|
| `standalone` | One company tracking its own assets. No MSP layer. | No |
| `selfhosted` | MSP managing multiple client organisations from one instance. | Yes — wildcard `*.yourdomain.com` |
| `saas` | Hosted SaaS — enables tier limits and Stripe billing. | Yes |
| `demo` | Public demo with scheduled data resets. | Yes |

If you're unsure, start with **standalone**. You can always re-deploy as MSP later.

---

## 2. Prerequisites

### Docker (easiest path)

| Requirement | Minimum version |
|-------------|----------------|
| Docker Engine | 24+ |
| Docker Compose | v2 (bundled with Docker Desktop and modern Docker Engine installs) |

Check: `docker compose version`

### Bare-metal

| Requirement | Minimum version |
|-------------|----------------|
| Python | 3.10 |
| pip | any recent |
| MariaDB or SQLite | MariaDB 10.6+ recommended for production |

---

## 3. Docker (recommended)

### Clone the repo

```bash
git clone https://github.com/your-org/tether.git
cd tether
cp .env.example .env
```

---

### Standalone — single company

Edit `.env` with these minimum values:

```dotenv
DEPLOYMENT_MODE=standalone

# Security — generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace-with-a-long-random-string

# Your admin login
ADMIN_EMAIL=you@yourcompany.com
ADMIN_PASSWORD=changeme
ADMIN_NAME=Your Name

# Your company details
DEFAULT_TENANT_NAME=Your Company
DEFAULT_TENANT_SLUG=yourcompany

# Database — docker-compose includes MariaDB, just set these two
DB_ROOT_PASSWORD=a-strong-root-password
DB_PASSWORD=a-strong-app-password
```

Start everything:

```bash
docker compose up -d
```

Open `http://localhost:8000` and log in with your `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

---

### MSP — multiple clients

Edit `.env`:

```dotenv
DEPLOYMENT_MODE=selfhosted

SECRET_KEY=replace-with-a-long-random-string

# Your root domain — clients get subdomains like acme.yourdomain.com
BASE_DOMAIN=yourdomain.com
APP_URL=https://yourdomain.com

# MSP admin login
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=changeme
ADMIN_NAME=MSP Admin

# Database
DB_ROOT_PASSWORD=a-strong-root-password
DB_PASSWORD=a-strong-app-password
```

Start:

```bash
docker compose up -d
```

Log in at `http://yourdomain.com` (or `http://localhost:8000` during local testing), create your first client tenant, and navigate to it via its subdomain.

> **MSP mode requires wildcard DNS.** See [DNS setup](#5-dns-setup) before exposing to the internet.

---

### Verifying Docker containers are healthy

```bash
docker compose ps
```

All three containers (`tether-app`, `tether-db`, `tether-redis`) should show `healthy` or `running`. If the app container shows `restarting`, check logs:

```bash
docker compose logs app --tail 50
```

---

## 4. Bare-metal (Linux)

Use the included installer script. It creates a Python virtualenv, installs all dependencies, generates a `.env` with a random secret key, and optionally registers a `systemd` service.

### Quick install

```bash
git clone https://github.com/your-org/tether.git
cd tether
./install.sh
```

The script will print instructions to start the server manually:

```bash
source .venv/bin/activate
cd backend
export $(grep -v '^#' ../.env | xargs)
export TETHER_DATA=../data
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Install as a systemd service (starts on boot)

```bash
sudo ./install.sh --service
```

This creates `/etc/systemd/system/tether.service` and starts it immediately.

```bash
# Check status
systemctl status tether

# View logs
journalctl -u tether -f

# Restart
sudo systemctl restart tether
```

### Bare-metal database setup

By default, Tether uses **SQLite** (zero setup — a file is created at `data/tether.db`). For production, switch to MariaDB:

```bash
sudo apt install -y mariadb-server

sudo mysql <<'SQL'
CREATE DATABASE tether CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tether'@'localhost' IDENTIFIED BY 'yourpassword';
GRANT ALL PRIVILEGES ON tether.* TO 'tether'@'localhost';
FLUSH PRIVILEGES;
SQL
```

Add to `.env`:

```dotenv
DB_HOST=localhost
DB_USER=tether
DB_PASSWORD=yourpassword
DB_NAME=tether
```

Then restart Tether. The schema is created automatically on first start.

---

## 5. DNS setup

### Standalone mode

Point a single A record at your server:

| Type | Name | Value |
|------|------|-------|
| A | `yourdomain.com` | `<server IP>` |

### MSP / SaaS mode

Tether needs two records — one for the root domain and a wildcard for all client subdomains:

| Type | Name | Value |
|------|------|-------|
| A | `yourdomain.com` | `<server IP>` |
| A | `*.yourdomain.com` | `<server IP>` |

The wildcard means every new client subdomain (`acme.yourdomain.com`, `nexus.yourdomain.com`) resolves automatically without manual DNS changes.

Set `BASE_DOMAIN=yourdomain.com` in `.env` to match.

> **TTL tip:** Use a short TTL (300 s) while setting up, then raise it to 3600+ once everything is confirmed working.

---

## 6. Reverse proxy (HTTPS)

Tether runs on port `8000`. In production, put it behind a reverse proxy to handle TLS termination and serve HTTPS on port 443.

### Caddy

Caddy automatically provisions and renews Let's Encrypt certificates.

**Standalone:**

```
yourdomain.com {
    reverse_proxy localhost:8000
}
```

**MSP (wildcard — requires DNS challenge):**

```
yourdomain.com, *.yourdomain.com {
    tls {
        dns cloudflare {env.CF_API_TOKEN}
    }
    reverse_proxy localhost:8000
}
```

Replace `cloudflare` with your DNS provider's Caddy plugin. See the [Caddy DNS modules list](https://caddyserver.com/docs/modules/).

### Nginx

**Standalone:**

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass         http://localhost:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

**MSP (wildcard subdomains):**

```nginx
# HTTP → HTTPS redirect for root and all subdomains
server {
    listen 80;
    server_name yourdomain.com *.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com *.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass         http://localhost:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

Wildcard TLS certificates require a DNS challenge. Use `certbot` with your DNS provider plugin:

```bash
# Example: Cloudflare
sudo apt install python3-certbot-dns-cloudflare
sudo certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials ~/.secrets/cloudflare.ini \
  -d yourdomain.com \
  -d "*.yourdomain.com"
```

---

## 7. Environment variable reference

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(insecure built-in)* | Signs JWT tokens. **Must be set in production.** Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DEPLOYMENT_MODE` | `selfhosted` | `selfhosted` · `standalone` · `saas` · `demo` |
| `BASE_DOMAIN` | `usetether.ca` | Root domain for subdomain routing. Set to your domain in MSP/SaaS mode. |
| `APP_URL` | `https://usetether.ca` | Public URL — used in email links and invite URLs |
| `ALLOW_SIGNUP` | `false` | Set `true` to enable public self-signup |
| `TETHER_DATA` | `./data` | Directory for SQLite DB and uploads (bare-metal only) |

### Admin account (first run only)

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_EMAIL` | `admin@usetether.ca` | Login email for the initial admin |
| `ADMIN_PASSWORD` | `admin` | **Change this.** Password for the initial admin |
| `ADMIN_NAME` | `MSP Admin` | Display name for the initial admin |

### Default tenant (first run only)

| Variable | Default (standalone) | Default (MSP) | Description |
|----------|---------------------|---------------|-------------|
| `DEFAULT_TENANT_NAME` | `My Company` | `Demo Client` | Company or first tenant name |
| `DEFAULT_TENANT_SLUG` | `mycompany` | `demo` | URL slug / subdomain |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(auto-built)* | Full connection string. Overrides all `DB_*` vars. |
| `DB_HOST` | *(unset → SQLite)* | MariaDB/MySQL host |
| `DB_PORT` | `3306` | MariaDB/MySQL port |
| `DB_NAME` | `tether` | Database name |
| `DB_USER` | *(unset)* | Database user |
| `DB_PASSWORD` | *(unset)* | Database password |
| `DB_ROOT_PASSWORD` | *(required by docker-compose)* | MariaDB root password (Docker only) |

### Email

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_PROVIDER` | `none` | `none` · `smtp` · `resend` · `sendgrid` |
| `EMAIL_FROM` | `noreply@usetether.ca` | From address |
| `EMAIL_FROM_NAME` | `Tether` | From display name |
| `SMTP_HOST` | `localhost` | SMTP hostname |
| `SMTP_PORT` | `587` | SMTP port (587 = STARTTLS, 465 = SSL) |
| `SMTP_USER` | *(unset)* | SMTP username |
| `SMTP_PASSWORD` | *(unset)* | SMTP password |
| `RESEND_API_KEY` | *(unset)* | API key for Resend |
| `SENDGRID_API_KEY` | *(unset)* | API key for SendGrid |

### Backups

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_ENABLED` | `false` | Enable scheduled S3 backups |
| `BACKUP_INTERVAL_HOURS` | `24` | Backup frequency |
| `BACKUP_RETAIN_DAYS` | `30` | Days of backups to keep |
| `BACKUP_S3_BUCKET` | *(unset)* | S3 bucket name |
| `BACKUP_S3_REGION` | `us-east-1` | S3 region |
| `BACKUP_S3_PREFIX` | `backups/` | Key prefix for backup objects |
| `BACKUP_S3_ACCESS_KEY` | *(unset)* | S3 access key |
| `BACKUP_S3_SECRET_KEY` | *(unset)* | S3 secret key |

### Warranty alerts

| Variable | Default | Description |
|----------|---------|-------------|
| `WARRANTY_ALERTS_ENABLED` | `true` | Email alerts for expiring warranties |
| `WARRANTY_ALERT_DAYS` | `30` | Days before expiry to trigger an alert |

### Rate limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_REDIS_URL` | *(unset → in-memory)* | Redis URL for distributed rate limiting across multiple app instances |

---

## 8. Database backends

Tether resolves the database in this priority order:

1. `DATABASE_URL` — explicit full connection string, always wins
2. `DB_HOST` + `DB_USER` — connects to MariaDB/MySQL
3. SQLite — automatic fallback, zero configuration

### SQLite

Good for: evaluation, development, low-traffic single-user installs.

No configuration needed. A file is created automatically at the path set by `TETHER_DATA` (Docker: `/data/tether.db`, bare-metal: `./data/tether.db`).

### MariaDB (recommended for production)

Included in `docker-compose.yml` — `docker compose up` starts it automatically.

For bare-metal, see [Bare-metal database setup](#bare-metal-database-setup).

### PostgreSQL

```dotenv
DATABASE_URL=postgresql://user:password@host:5432/tether
```

Tether creates all tables on first start. No manual schema steps required.

### Schema migrations

Tether applies `ALTER TABLE` migrations automatically on startup. New columns added in later versions are added to existing databases without manual intervention. The app handles both SQLite (`try/except` pattern) and MariaDB/PostgreSQL (`ADD COLUMN IF NOT EXISTS`).

---

## 9. Email setup

Email is optional but needed for: password resets, invite links, asset request notifications, and warranty alerts.

Set `EMAIL_PROVIDER` to one of the options below and restart.

### SMTP (any provider)

```dotenv
EMAIL_PROVIDER=smtp
EMAIL_FROM=noreply@yourdomain.com
EMAIL_FROM_NAME=Tether
SMTP_HOST=smtp.yourprovider.com
SMTP_PORT=587
SMTP_USER=your-smtp-username
SMTP_PASSWORD=your-smtp-password
```

Common SMTP settings:

| Provider | Host | Port |
|----------|------|------|
| Gmail (App Password) | `smtp.gmail.com` | `587` |
| Outlook / Microsoft 365 | `smtp.office365.com` | `587` |
| Mailgun | `smtp.mailgun.org` | `587` |
| Postmark | `smtp.postmarkapp.com` | `587` |

> Gmail: enable 2FA and create an [App Password](https://myaccount.google.com/apppasswords) rather than using your account password.

### Resend

```dotenv
EMAIL_PROVIDER=resend
EMAIL_FROM=noreply@yourdomain.com
RESEND_API_KEY=re_...
```

### SendGrid

```dotenv
EMAIL_PROVIDER=sendgrid
EMAIL_FROM=noreply@yourdomain.com
SENDGRID_API_KEY=SG....
```

### No email

```dotenv
EMAIL_PROVIDER=none
```

All email operations are silently skipped. Password reset still works — the reset token is logged to the server console so you can retrieve it manually during testing.

---

## 10. Automated backups

Tether can back up the database on a schedule to any S3-compatible object storage: AWS S3, Backblaze B2, Cloudflare R2, DigitalOcean Spaces, or MinIO.

```dotenv
BACKUP_ENABLED=true
BACKUP_INTERVAL_HOURS=24
BACKUP_RETAIN_DAYS=30

BACKUP_S3_BUCKET=my-tether-backups
BACKUP_S3_REGION=us-east-1
BACKUP_S3_ACCESS_KEY=AKIAxxx
BACKUP_S3_SECRET_KEY=xxx
```

For Cloudflare R2 or other S3-compatible providers, set `DATABASE_URL` to include the custom endpoint, or configure `BACKUP_S3_ENDPOINT` if your provider requires a non-AWS endpoint URL.

Backups are timestamped and stored under `BACKUP_S3_PREFIX` (default: `backups/`). Files older than `BACKUP_RETAIN_DAYS` are automatically deleted.

---

## 11. First login and initial configuration

### Default credentials

| Mode | URL | Email | Password |
|------|-----|-------|----------|
| `standalone` | `http://localhost:8000` | value of `ADMIN_EMAIL` | value of `ADMIN_PASSWORD` |
| `selfhosted` / `saas` | `http://localhost:8000` (root domain) | `admin@usetether.ca` | `admin` |

**Change your password immediately** after the first login. Go to **Settings → Change Password**.

Also set a proper `SECRET_KEY` in `.env` and restart before exposing the app on a public network. The default key is not secret.

### Initial setup checklist

1. **Change the admin password** — Settings → Change Password
2. **Set your company name and logo** — Settings → General
3. **Configure email** — Settings → Email (needed for invites and password resets)
4. **Create categories and locations** — Settings → Categories / Settings → Locations
5. **Add users** — Users → Invite User (sends an email invite with a one-time link)
6. **Import existing assets** — Assets → Import CSV

### MSP: adding client tenants

1. Log in as MSP admin at the root domain
2. Go to **Clients → New Client**
3. Give the client a name and slug (e.g. slug `acme` → subdomain `acme.yourdomain.com`)
4. Navigate into the client by clicking their name, or visit their subdomain directly
5. Invite the client's admin user via **Users → Invite User** while scoped to their tenant

---

## 12. Updating

### Docker

Your data lives in Docker named volumes. They survive rebuilds and are never touched by `docker compose down` or `docker compose build`.

```bash
git pull
docker compose down
docker compose build --no-cache
docker compose up -d
```

Schema migrations run automatically on startup. No manual SQL steps needed.

> **Do not run `docker compose down -v`** — the `-v` flag deletes volumes and destroys your data.

### Bare-metal

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart tether
```

---

## 13. Backup and restore

### Manual backup

```bash
# Docker — MariaDB
docker exec tether-db sh -c \
  "mysqldump -u tether -p\$MARIADB_PASSWORD tether" \
  > tether-$(date +%Y%m%d).sql

# Docker — SQLite (only if not using MariaDB)
docker run --rm \
  -v tether_data:/data \
  -v $(pwd):/backup \
  alpine cp /data/tether.db /backup/tether-$(date +%Y%m%d).db

# Bare-metal — SQLite
cp data/tether.db backups/tether-$(date +%Y%m%d).db

# Bare-metal — MariaDB
mysqldump -u tether -p tether > tether-$(date +%Y%m%d).sql
```

### Restore

```bash
# Docker — MariaDB
docker exec -i tether-db sh -c \
  "mysql -u tether -p\$MARIADB_PASSWORD tether" \
  < tether-20240101.sql

# Docker — SQLite
docker compose down
docker run --rm \
  -v tether_data:/data \
  -v $(pwd):/backup \
  alpine cp /backup/tether-20240101.db /data/tether.db
docker compose up -d

# Bare-metal — SQLite
systemctl stop tether
cp backups/tether-20240101.db data/tether.db
systemctl start tether

# Bare-metal — MariaDB
mysql -u tether -p tether < tether-20240101.sql
sudo systemctl restart tether
```

---

## 14. Troubleshooting

### Container won't start

```bash
docker compose logs app --tail 100
```

Common causes:

| Error | Fix |
|-------|-----|
| `SECRET_KEY must be set` | Add `SECRET_KEY=...` to `.env` |
| `DB_PASSWORD must be set` | Add `DB_PASSWORD=...` to `.env` |
| `ADMIN_EMAIL must be set` | Add `ADMIN_EMAIL=...` to `.env` |
| `Database unavailable after 10 attempts` | MariaDB container isn't ready — usually resolves on a second `docker compose up -d`. Check MariaDB logs: `docker compose logs db` |
| `Unknown column '...' in SELECT` | Schema migration failed. Check app logs for the specific column. Ensure the app user has `ALTER TABLE` permission. |

### App starts but login fails

- Confirm `ADMIN_EMAIL` and `ADMIN_PASSWORD` match what you set before the first run. These are only used to seed the database on the initial startup. If you've already run the app with different values, use the existing credentials or reset the password directly in the database.
- Confirm the JWT `SECRET_KEY` hasn't changed since you last logged in — changing it invalidates all existing tokens.

### MSP: client subdomain not working

1. Check DNS — `dig acme.yourdomain.com` should resolve to your server IP.
2. Check `BASE_DOMAIN` in `.env` matches your actual domain.
3. If using a reverse proxy, confirm it's passing the `Host` header through (`proxy_set_header Host $host`).

### Emails not sending

1. Set `EMAIL_PROVIDER=none` temporarily and check if a password reset token appears in the server logs (`journalctl -u tether -f` or `docker compose logs app -f`).
2. If `EMAIL_PROVIDER=smtp`, test with a tool like `swaks`:
   ```bash
   swaks --to test@example.com \
         --server smtp.yourprovider.com:587 \
         --auth LOGIN \
         --auth-user your-smtp-user \
         --auth-password your-smtp-password \
         --tls
   ```

### Resetting the admin password

If you've lost the admin password, update it directly in the database. First get the bcrypt hash of your new password:

```bash
python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('newpassword'))"
```

Then update:

```bash
# Docker MariaDB
docker exec -it tether-db mysql -u tether -p tether \
  -e "UPDATE users SET password_hash='<hash>' WHERE email='admin@usetether.ca';"

# Bare-metal SQLite
sqlite3 data/tether.db \
  "UPDATE users SET password_hash='<hash>' WHERE email='admin@usetether.ca';"
```

### Viewing the API docs

The full interactive API reference is available at `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` while the server is running. All endpoints are documented with request/response schemas.
