# Tether

A modern, self-hostable IT asset management platform for MSPs and IT teams. Manage multiple client tenants, track hardware, handle check-outs, generate QR labels, and import/export via CSV — all from a clean web interface.

---

## Features

- **Asset tracking** — tag, name, serial, model, manufacturer, status, purchase cost, warranty expiry
- **Check-out / check-in** — assign assets to people with a full audit trail
- **Asset requests** — employees can submit requests; admins approve or deny
- **Dashboard** — total assets, value, status breakdown charts, expiring warranties
- **QR labels** — per-asset QR codes downloadable as PNG
- **CSV import/export** — bulk-load assets; categories, locations, and people are created automatically
- **Search & filter** — by keyword, status, category, location; sortable columns
- **Multi-tenant (MSP)** — manage multiple client organisations from a single instance; each tenant gets its own subdomain
- **User management** — role-based permissions, per-user overrides, invite-based onboarding
- **Password reset** — self-service via email token
- **Billing** — Stripe-backed subscription management
- **Email notifications** — supports SMTP, Resend, and SendGrid
- **Warranty alerts** — scheduled alerts for assets expiring within a configurable window
- **Automated backups** — scheduled S3-compatible backup of the database
- **Rate limiting** — in-memory or Redis-backed rate limits on auth endpoints

---

## Quick Start

### Docker (recommended)

**Requirements:** Docker + Docker Compose

```bash
# 1. Copy and edit the environment file
cp .env.example .env
#    Set a real SECRET_KEY and change ADMIN_PASSWORD before exposing to a network

# 2. Start
docker compose up -d

# 3. Open
open http://localhost:8000
```

The database is stored in a named Docker volume (`tether_data`) and survives restarts and container rebuilds.

To stop:
```bash
docker compose down
```

To update after pulling new code:
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

### Bare-metal (Linux / macOS)

**Requirements:** Python 3.10 or newer

```bash
# 1. Run the installer (creates a .venv, installs deps, generates .env)
./install.sh

# 2. Edit .env if you want to change the admin password or secret key
nano .env

# 3. Start the server
source .venv/bin/activate
cd backend
export $(grep -v '^#' ../.env | xargs)
export TETHER_DATA=../data
uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Open
open http://localhost:8000
```

#### Install as a systemd service (starts on boot)

```bash
sudo ./install.sh --service
# Check status
systemctl status tether
```

---

## Default Login

| Username | Password |
|----------|----------|
| `admin@usetether.ca` | `admin` |

**Change the password immediately** via Settings → Change Password, and set a proper `SECRET_KEY` in `.env` before exposing the app on a network.

---

## Environment Variables

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(insecure default)* | Secret for signing JWT tokens. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `BASE_DOMAIN` | `usetether.ca` | Root domain. Client subdomains are derived from this — e.g. `acme.usetether.ca` |
| `APP_URL` | `https://usetether.ca` | Public URL of the app, used in emails and invite links |
| `DEPLOYMENT_MODE` | `selfhosted` | Set to `demo` to enable demo mode |
| `ALLOW_SIGNUP` | `false` | Set to `true` to enable public sign-up |
| `ADMIN_EMAIL` | `admin@usetether.ca` | Email for the initial MSP admin account (first run only) |
| `ADMIN_PASSWORD` | `admin` | Password for the initial MSP admin account (first run only) |
| `ADMIN_NAME` | `MSP Admin` | Display name for the initial MSP admin |
| `DEFAULT_TENANT_SLUG` | `demo` | Slug for the demo tenant created on first run |
| `DEFAULT_TENANT_NAME` | `Demo Client` | Name for the demo tenant created on first run |
| `TETHER_DATA` | `./data` | Directory where the SQLite database is stored |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(auto-built)* | Full connection string — overrides all `DB_*` vars. Supports `mysql+pymysql://`, `postgresql://`, or `sqlite:///` |
| `DB_HOST` | *(unset)* | MariaDB/MySQL host. When set, Tether connects to MariaDB instead of SQLite |
| `DB_PORT` | `3306` | MariaDB/MySQL port |
| `DB_NAME` | `tether` | Database name |
| `DB_USER` | *(unset)* | Database username |
| `DB_PASSWORD` | *(unset)* | Database password |

### Email

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_PROVIDER` | `none` | Email backend: `none`, `smtp`, `resend`, or `sendgrid` |
| `EMAIL_FROM` | `noreply@usetether.ca` | From address for outgoing emails |
| `EMAIL_FROM_NAME` | `Tether` | Display name for outgoing emails |
| `SMTP_HOST` | `localhost` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | *(unset)* | SMTP username |
| `SMTP_PASSWORD` | *(unset)* | SMTP password |
| `RESEND_API_KEY` | *(unset)* | API key for Resend |
| `SENDGRID_API_KEY` | *(unset)* | API key for SendGrid |

### Backup

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_ENABLED` | `false` | Set to `true` to enable scheduled S3 backups |
| `BACKUP_INTERVAL_HOURS` | `24` | How often to run a backup |
| `BACKUP_RETAIN_DAYS` | `30` | How many days of backups to keep |
| `BACKUP_S3_BUCKET` | *(unset)* | S3 bucket name |
| `BACKUP_S3_REGION` | `us-east-1` | S3 region |
| `BACKUP_S3_PREFIX` | `backups/` | Key prefix for backup objects |
| `BACKUP_S3_ACCESS_KEY` | *(unset)* | S3 access key |
| `BACKUP_S3_SECRET_KEY` | *(unset)* | S3 secret key |

### Warranty Alerts

| Variable | Default | Description |
|----------|---------|-------------|
| `WARRANTY_ALERTS_ENABLED` | `true` | Send email alerts for expiring warranties |
| `WARRANTY_ALERT_DAYS` | `30` | Days before expiry to send an alert |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_REDIS_URL` | *(unset)* | Redis URL for distributed rate limiting. Falls back to in-memory if unset |

---

## DNS Setup

Tether uses subdomains to separate clients. You need two DNS records pointing to your server:

| Type | Name | Value |
|------|------|-------|
| A | `usetether.ca` | your server IP |
| A | `*.usetether.ca` | your server IP |

The wildcard `*` record means every client subdomain (`acme.usetether.ca`, `nexus.usetether.ca`, etc.) resolves automatically without adding a record per client.

If you're running Tether on a different domain, set `BASE_DOMAIN` in your `.env` to match and add the equivalent DNS records.

---

## Database

Tether supports three database backends. The priority order is:

1. **`DATABASE_URL`** — if set explicitly, always used
2. **MariaDB/MySQL** — used when `DB_HOST` and `DB_USER` are set
3. **SQLite** — zero-config fallback, used automatically if neither of the above is set

### MariaDB (recommended for production)

Tether is designed with MariaDB as the preferred production database, consistent with tools like Snipe-IT that MSPs are already familiar with.

**Docker:** MariaDB is included automatically — `docker compose up` starts both the app and a MariaDB 11 container with no extra setup.

**Bare-metal:**
```bash
sudo apt install -y mariadb-server
sudo mysql -e "CREATE DATABASE tether CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -e "CREATE USER 'tether'@'localhost' IDENTIFIED BY 'yourpassword';"
sudo mysql -e "GRANT ALL PRIVILEGES ON tether.* TO 'tether'@'localhost'; FLUSH PRIVILEGES;"
```

Then set in `.env`:
```
DB_HOST=localhost
DB_USER=tether
DB_PASSWORD=yourpassword
DB_NAME=tether
```

### SQLite (zero-config)

Leave `DB_HOST` unset and Tether creates a SQLite file at `data/tether.db`. No installation required. Good for evaluation, development, or low-traffic self-hosted installs.

### PostgreSQL

```
DATABASE_URL=postgresql://user:pass@host:5432/tether
```

---

## CSV Import Format

Use **Assets → Import** to bulk-load assets. The CSV must have a header row. Only `asset_tag` is required; all other columns are optional.

```
asset_tag,name,manufacturer,model,serial,category,location,status,assigned_to,purchase_date,purchase_cost,warranty_expiry,notes
IT-0001,MacBook Pro 16,Apple,M3 Max,C02XY1234,Laptop,Head Office,deployed,Jane Smith,2024-03-01,3499,2027-03-01,
IT-0002,Dell Monitor,Dell,U2724DE,,Monitor,Remote,available,,,620,,
```

- **category**, **location**, and **assigned_to** are created automatically if they don't exist
- **status** must be one of: `available`, `deployed`, `maintenance`, `retired` (defaults to `available`)
- **purchase_date** and **warranty_expiry** accept `YYYY-MM-DD`, `MM/DD/YYYY`, or `DD/MM/YYYY`
- Rows with an existing `asset_tag` are **updated**, not duplicated

---

## Running Tests

```bash
pip install -r requirements.txt pytest
pytest tests/ -v
```

Tests use SQLite in a temp directory — no database setup required.

---

## Project Structure

```
tether/
├── backend/
│   ├── main.py               # FastAPI app, router registration
│   ├── security.py           # JWT auth, bcrypt, permissions
│   ├── email_service.py      # SMTP / Resend / SendGrid abstraction
│   ├── billing.py            # Billing helpers
│   ├── backup_service.py     # Scheduled S3 backup
│   ├── rate_limit.py         # In-memory / Redis rate limiting
│   ├── scheduler.py          # Warranty alert scheduler
│   ├── db/database.py        # DB setup, connection, seeding
│   ├── models/models.py      # SQLAlchemy models
│   ├── schemas/schemas.py    # Pydantic request/response schemas
│   └── routers/
│       ├── auth.py           # Login, /me, change-password
│       ├── signup.py         # Public sign-up
│       ├── password_reset.py # Self-service password reset
│       ├── assets.py         # CRUD, checkout/checkin, QR, CSV
│       ├── categories.py     # Asset categories
│       ├── locations.py      # Asset locations
│       ├── users.py          # People / employees
│       ├── requests.py       # Asset requests
│       ├── dashboard.py      # Stats endpoint
│       ├── tenants.py        # Tenant management
│       ├── user_mgmt.py      # User CRUD, roles, permissions
│       ├── invites.py        # Invite-based onboarding
│       ├── billing_router.py # Billing endpoints
│       ├── stripe_router.py  # Stripe webhooks
│       ├── admin_router.py   # Admin panel
│       └── demo.py           # Demo mode (DEPLOYMENT_MODE=demo only)
├── frontend/
│   ├── templates/index.html  # SPA shell
│   └── static/
│       ├── css/style.css
│       └── js/
│           ├── app.js        # API layer, auth, router, helpers
│           ├── views.js      # Login, shell, dashboard
│           ├── views2.js     # Assets, categories, locations, people, settings
│           ├── icons.js      # Inline SVG icon set
│           └── chart.umd.js  # Chart.js (vendored, no CDN required)
├── tests/
│   ├── conftest.py           # Shared fixtures (client, auth, tenant)
│   ├── test_admin.py
│   ├── test_assets.py
│   ├── test_auth.py
│   ├── test_billing.py
│   ├── test_categories.py
│   ├── test_dashboard.py
│   ├── test_employees.py
│   ├── test_locations.py
│   ├── test_password_reset.py
│   ├── test_public.py
│   ├── test_requests.py
│   ├── test_signup.py
│   ├── test_stripe.py
│   ├── test_tenants.py
│   └── test_users.py
├── Dockerfile
├── docker-compose.yml
├── install.sh
├── requirements.txt
└── .env.example
```

---

## API

Interactive API docs are available at `http://localhost:8000/docs` when the server is running.

All endpoints under `/api/*` (except `/api/auth/login` and `/api/assets/{id}/qr`) require a Bearer token obtained from `POST /api/auth/login`.

---

## Backup

The entire database is a single file. To back it up manually:

```bash
# Docker
docker run --rm -v tether_data:/data -v $(pwd):/backup alpine \
  cp /data/tether.db /backup/tether-$(date +%Y%m%d).db

# Bare-metal
cp data/tether.db backups/tether-$(date +%Y%m%d).db
```

To restore, stop the server, replace the file, and restart.

For automated backups to S3, set `BACKUP_ENABLED=true` and the `BACKUP_S3_*` variables in `.env`.

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy
- **Database:** SQLite (default) · MariaDB · PostgreSQL
- **Auth:** bcrypt + JWT (python-jose)
- **Frontend:** Vanilla JS SPA, Chart.js (vendored)
- **Fonts:** Bricolage Grotesque + IBM Plex Sans + IBM Plex Mono

---

## License

MIT
