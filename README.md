# Tether

A modern, self-hostable IT asset management tool. Run it as a **single company** tracking your own hardware, or as an **MSP** managing multiple client organisations from one instance.

---

## Features

- **Asset tracking** — tag, name, serial, model, manufacturer, status, purchase cost, warranty expiry
- **Check-out / check-in** — assign assets to people with a full audit trail
- **Asset requests** — employees can submit requests; admins approve or deny
- **Dashboard** — total assets, value, status breakdown charts, expiring warranties
- **QR labels** — per-asset QR codes downloadable as PNG
- **CSV import/export** — bulk-load assets; categories, locations, and people are created automatically
- **Search & filter** — by keyword, status, category, location; sortable columns
- **Standalone mode** — single-company deployment with no MSP layer; one login, one dashboard
- **Multi-tenant (MSP)** — manage multiple client organisations from one instance; each tenant gets its own subdomain
- **Preview as client** — MSP admins can open any client's view in a new tab with one click
- **User management** — role-based permissions, per-user overrides, invite-based onboarding
- **Password reset** — self-service via email token
- **Billing** — Stripe-backed subscription management
- **Email notifications** — supports SMTP, Resend, and SendGrid
- **Warranty alerts** — scheduled alerts for assets expiring within a configurable window
- **Automated backups** — scheduled S3-compatible backup of the database
- **Rate limiting** — in-memory or Redis-backed rate limits on auth endpoints

---

## Deployment Modes

Set `DEPLOYMENT_MODE` in `.env` to choose how Tether runs:

| Mode | Who it's for |
|------|-------------|
| `selfhosted` | **MSP / default** — manage multiple client companies from one instance. Each client gets a subdomain. Requires wildcard DNS. |
| `standalone` | **Single company** — your company is the only tenant. No MSP layer, no subdomain routing. Just log in and track your assets. |
| `saas` | Hosted SaaS — tier limits and billing UI enabled. |
| `demo` | Public demo — data resets on a schedule via the Cloudflare Worker integration. |

---

## Quick Start

### Standalone (single company)

The simplest setup — no subdomain DNS needed.

**`.env` minimum config:**
```
DEPLOYMENT_MODE=standalone
SECRET_KEY=your-long-random-string
ADMIN_EMAIL=you@yourcompany.com
ADMIN_PASSWORD=changeme
DEFAULT_TENANT_NAME=Your Company Name
DEFAULT_TENANT_SLUG=yourcompany
```

```bash
cp .env.example .env
# edit the values above
docker compose up -d
open http://localhost:8000
```

Log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`. You land directly on your company dashboard — no MSP screens.

---

### MSP (multiple clients)

**`.env` minimum config:**
```
DEPLOYMENT_MODE=selfhosted
SECRET_KEY=your-long-random-string
BASE_DOMAIN=yourdomain.com
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=changeme
```

**Requirements:** Docker + Docker Compose, wildcard DNS (`*.yourdomain.com` → your server)

```bash
cp .env.example .env
docker compose up -d
open http://localhost:8000
```

Log in as the MSP admin, create client tenants, and navigate to each via their subdomain.

---

### Docker commands

```bash
# Stop
docker compose down

# Restart (keeps data)
docker compose up -d
```

---

### Updating (Docker)

Your data lives in Docker **named volumes** — it survives container rebuilds and image changes. Updating never touches these volumes.

```bash
git pull                          # fetch new code
docker compose down               # stop running containers (data is safe)
docker compose build --no-cache   # rebuild the app image
docker compose up -d              # start with new image
```

The app runs database migrations automatically on startup, so no manual SQL steps are needed.

> **Do not** use `docker compose down -v` — the `-v` flag deletes volumes and **will destroy your data**.

---

### Bare-metal (Linux / macOS)

**Requirements:** Python 3.10 or newer

```bash
# 1. Run the installer (creates a .venv, installs deps, generates .env)
./install.sh

# 2. Edit .env — set DEPLOYMENT_MODE, SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
nano .env

# 3. Start the server
source .venv/bin/activate
cd backend
export $(grep -v '^#' ../.env | xargs)
export TETHER_DATA=../data
uvicorn main:app --host 0.0.0.0 --port 8000
```

#### Install as a systemd service (starts on boot)

```bash
sudo ./install.sh --service
systemctl status tether
```

### Updating (bare-metal)

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt   # pick up any new dependencies
sudo systemctl restart tether     # or however you run the process
```

The app migrates the database on startup — no manual SQL steps needed.

---

## Default Login

The first-run admin account is controlled by `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env`.

| Mode | Default email | Default password |
|------|--------------|-----------------|
| `standalone` | value of `ADMIN_EMAIL` | value of `ADMIN_PASSWORD` |
| `selfhosted` / `saas` | `admin@usetether.ca` | `admin` |

**Change the password immediately** via Settings → Change Password, and set a proper `SECRET_KEY` before exposing the app on a network.

---

## Environment Variables

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(insecure default)* | Secret for signing JWT tokens. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DEPLOYMENT_MODE` | `selfhosted` | `selfhosted` · `standalone` · `saas` · `demo` — see [Deployment Modes](#deployment-modes) |
| `BASE_DOMAIN` | `usetether.ca` | Root domain for subdomain routing (MSP/SaaS only). Not required in standalone mode. |
| `APP_URL` | `https://usetether.ca` | Public URL of the app, used in emails and invite links |
| `ALLOW_SIGNUP` | `false` | Set to `true` to enable public sign-up |
| `TETHER_DATA` | `./data` | Directory where the SQLite database is stored |

### Admin account (first run only)

In `selfhosted`/`saas` mode this creates the MSP admin. In `standalone` mode this creates your company admin.

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_EMAIL` | `admin@usetether.ca` | Login email for the initial admin account |
| `ADMIN_PASSWORD` | `admin` | Password for the initial admin account |
| `ADMIN_NAME` | `Admin` | Display name for the initial admin account |

### Company / default tenant (first run only)

In `standalone` mode this is your company. In MSP mode this is the first demo/default client tenant.

| Variable | Default (standalone) | Default (MSP) | Description |
|----------|---------------------|---------------|-------------|
| `DEFAULT_TENANT_NAME` | `My Company` | `Demo Client` | Company or tenant name |
| `DEFAULT_TENANT_SLUG` | `mycompany` | `demo` | URL slug — used for subdomain routing in MSP mode |

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

**Standalone mode:** no special DNS needed. Point your domain at the server with a single A record.

**MSP / SaaS mode:** Tether uses subdomains to separate clients. You need two records:

| Type | Name | Value |
|------|------|-------|
| A | `yourdomain.com` | your server IP |
| A | `*.yourdomain.com` | your server IP |

The wildcard record means every client subdomain (`acme.yourdomain.com`, `nexus.yourdomain.com`, etc.) resolves automatically without adding a record per client.

Set `BASE_DOMAIN` in `.env` to match your domain.

---

## Database

Tether supports three database backends. The priority order is:

1. **`DATABASE_URL`** — if set explicitly, always used
2. **MariaDB/MySQL** — used when `DB_HOST` and `DB_USER` are set
3. **SQLite** — zero-config fallback, used automatically if neither of the above is set

### MariaDB (recommended for production)

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

Leave `DB_HOST` unset and Tether creates a SQLite file at `data/tether.db`. No installation required. Good for evaluation, development, or low-traffic installs.

### PostgreSQL

```
DATABASE_URL=postgresql://user:pass@host:5432/tether
```

---

## MSP Features

### Navigating clients

- Click any **client name** in the dashboard or Clients page to jump straight into that client's view
- While inside a client, an **← All Clients** button appears in the sidebar to return to the MSP root

### Preview as client

Each client row in the Clients page has a **preview (eye) button**. Clicking it opens a new browser tab logged in as a read-only demo user for that tenant — letting you see exactly what that client's users see without sharing credentials or creating a real account. The preview session expires when the tab is closed.

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
│       ├── tenants.py        # Tenant management (MSP)
│       ├── user_mgmt.py      # User CRUD, roles, permissions
│       ├── invites.py        # Invite-based onboarding
│       ├── billing_router.py # Billing endpoints
│       ├── stripe_router.py  # Stripe webhooks
│       ├── admin_router.py   # Admin panel + preview-token endpoint
│       └── demo.py           # Demo mode (DEPLOYMENT_MODE=demo only)
├── frontend/
│   ├── templates/index.html  # SPA shell
│   └── static/
│       ├── css/style.css
│       └── js/
│           ├── app.js        # API layer, auth, router, helpers
│           ├── views.js      # Login, shell, dashboard, MSP views
│           ├── views2.js     # Assets, categories, locations, people, settings
│           ├── icons.js      # Inline SVG icon set
│           └── chart.umd.js  # Chart.js (vendored, no CDN required)
├── tests/
│   ├── conftest.py           # Shared fixtures (client, auth, tenant)
│   ├── test_admin.py         # Admin endpoints + preview-token
│   ├── test_assets.py
│   ├── test_auth.py
│   ├── test_billing.py
│   ├── test_categories.py
│   ├── test_dashboard.py
│   ├── test_employees.py
│   ├── test_locations.py
│   ├── test_password_reset.py
│   ├── test_public.py        # Public endpoints + standalone branding
│   ├── test_requests.py
│   ├── test_signup.py
│   ├── test_standalone.py    # Standalone mode seeding + login
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

## Data Storage

### Where data lives

| Setup | What's stored | Where |
|-------|--------------|-------|
| Docker + MariaDB (default) | All app data | Docker volume `tether_db` — inside MariaDB |
| Docker + SQLite fallback | SQLite file + uploads | Docker volume `tether_data` mounted at `/data` |
| Bare-metal | SQLite file + uploads | Directory set by `TETHER_DATA` env var (default `./data`) |

**Docker volumes are not deleted** by `docker compose down` or `docker compose build`. They persist until you explicitly run `docker volume rm` or `docker compose down -v`.

### Changing where data is stored (Docker)

To move MariaDB data to a host directory instead of a managed Docker volume, edit `docker-compose.yml`:

```yaml
# Before (managed Docker volume — data is inside Docker)
volumes:
  - tether_db:/var/lib/mysql

# After (bind mount — data is at /opt/tether/db on your host)
volumes:
  - /opt/tether/db:/var/lib/mysql
```

Do the same for app uploads / SQLite if needed:

```yaml
volumes:
  - /opt/tether/data:/data
```

Then stop, migrate the data, and restart:

```bash
docker compose down
# Copy existing volume contents to the new host path first
sudo mkdir -p /opt/tether/db
docker run --rm -v tether_db:/from -v /opt/tether/db:/to alpine sh -c "cp -a /from/. /to/"
docker compose up -d
```

### Changing the database backend

You can switch Tether from SQLite to MariaDB (or vice versa) at any time. The database is re-seeded only on the very first run (when the tables are empty), so switching backends on an existing install will start with a fresh database unless you migrate the data manually.

**SQLite → MariaDB:** set `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` in `.env` and restart. Tether creates the schema automatically.

**MariaDB → SQLite:** remove the `DB_HOST` / `DB_USER` / `DB_PASSWORD` vars (or set `DATABASE_URL=sqlite:///./data/tether.db`) and restart.

**Migrating data between backends** requires a manual dump/restore — use `mysqldump` for MariaDB exports, or a tool like `pgloader` for PostgreSQL.

---

## Backup

### Manual backup

```bash
# Docker — MariaDB
docker exec tether-db sh -c \
  "mysqldump -u tether -p\$MARIADB_PASSWORD tether" \
  > tether-$(date +%Y%m%d).sql

# Docker — SQLite (if using SQLite fallback)
docker run --rm -v tether_data:/data -v $(pwd):/backup alpine \
  cp /data/tether.db /backup/tether-$(date +%Y%m%d).db

# Bare-metal — SQLite
cp data/tether.db backups/tether-$(date +%Y%m%d).db
```

### Restore

```bash
# Docker — MariaDB
docker exec -i tether-db sh -c \
  "mysql -u tether -p\$MARIADB_PASSWORD tether" \
  < tether-20240101.sql

# Docker — SQLite
docker compose down
docker run --rm -v tether_data:/data -v $(pwd):/backup alpine \
  cp /backup/tether-20240101.db /data/tether.db
docker compose up -d

# Bare-metal — SQLite
systemctl stop tether
cp backups/tether-20240101.db data/tether.db
systemctl start tether
```

### Automated S3 backups

Set `BACKUP_ENABLED=true` and the `BACKUP_S3_*` variables in `.env` to enable scheduled backups to any S3-compatible storage (AWS S3, Backblaze B2, Cloudflare R2, DigitalOcean Spaces, MinIO).

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
