# Changelog

All notable changes to Tether are documented here.  
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Fixed
- **Schema migrations** — `init_db()` now runs `ALTER TABLE … ADD COLUMN IF NOT EXISTS` for every column added after the initial release. Existing MariaDB/PostgreSQL installs that pre-date a model change will have the missing columns added automatically on the next startup rather than crashing with `Unknown column` errors. SQLite uses a `try/except` fallback (no `IF NOT EXISTS` support). Covers the `email_from_*` columns on `tenants` and `useful_life_years`/`salvage_value` on `assets`.

### Added
- **Custom fields** — per-tenant key/value fields for assets (IMEI, VLAN, licence key, department code, etc.)
  - `CustomFieldDef` and `CustomFieldValue` models with cascade-delete
  - `GET/POST/PUT/DELETE /api/custom-fields/defs` — field definition management (requires `categories.manage`)
  - `GET/PUT /api/custom-fields/values/{asset_id}` — value upsert per asset (requires `assets.edit`)
  - `GET /api/assets/{id}` now includes a `custom_fields` list
  - CSV export includes custom field columns dynamically
  - CSV import auto-creates field defs for unknown column headers and upserts values
  - Settings page panel for managing field definitions (Add / Edit / Delete)
  - Asset form renders custom field inputs (text, number, date, boolean, url)
  - Asset detail view shows a Custom Fields panel; URL fields are clickable links, booleans render as Yes/No
  - `tests/test_custom_fields.py` — 13 tests covering CRUD, values, cascade, cross-tenant isolation, auth, CSV export

---

## [0.0.9] — 2026-06-07

### Fixed
- Deleting a tenant now correctly nullifies `AuditLog.actor_id` and `AuditLog.tenant_id` foreign key references before the cascade, preventing constraint violations on databases with strict FK enforcement. `InviteToken` and `AssetRequest` rows are also cleaned up explicitly before the tenant delete.

---

## [0.0.8] — 2026-06-07

### Added
- **Audit log** — every significant action (asset create/update/delete, checkout/checkin, user management, tenant management, CSV import, bulk operations) is recorded in a new `audit_logs` table
  - `audit.py` helper used throughout all routers
  - `GET /api/admin/audit-log` endpoint for MSP admins
- **Reports** — new `/api/reports` router with three report types:
  - `GET /api/reports/warranty` — assets with warranty expiring within N days
  - `GET /api/reports/assets-by-status` — count breakdown by status (with per-tenant breakdown for MSP)
  - `GET /api/reports/value` — total asset value, by-category and by-tenant breakdown, top 10 assets
  - `GET /api/reports/export` — CSV export for all three report types
- Reports page in the frontend with four cards (status, value, warranty, depreciation) and export menu
- **Depreciation tracking** — straight-line depreciation on assets
  - `useful_life_years` and `salvage_value` columns on `Asset`
  - `calculate_depreciation()` helper (annual depreciation, current book value, days remaining, fully-depreciated flag)
  - `GET /api/assets/{id}` includes a `depreciation` object (only on single-asset endpoint to avoid N+1)
  - `GET /api/reports/depreciation` and `GET /api/reports/depreciation/export`
  - Depreciation section in asset form (useful life, salvage value)
  - Depreciation panel on asset detail page (progress bar, end-of-life date, book value)
  - Depreciation card on Reports page
- **Activity feed** — `GET /api/assets/activity` merges `CheckoutLog` (checkout/checkin) and `AuditLog` (create/update/delete) events into a single chronological feed with filtering and pagination
  - Activity page (`pageActivity()`) with action-filter dropdown, asset search, timeline layout, Load More
  - "View all activity" link on tenant dashboard
- **Software licences** — `SoftwareLicence` and `LicenceAssignment` models; `/api/licences` router
  - Create, update, delete licence records (vendor, type, seat count, expiry, cost, licence key)
  - Assign/unassign seats to employees or assets; seat-cap enforcement
  - `GET /api/licences/expiring` for warranty-style alerts
  - Full UI in the Licences page
- **Email notifications for asset requests**
  - New request → notifies all active MSP staff (`send_request_notification()`)
  - Status change → notifies requester + client admins/managers (`send_request_update()`)
  - Both are non-blocking (wrapped in try/except; never abort the business operation)
  - White-label branding via `tenant=` kwarg
- **Client portal** — simplified three-tab view (Overview, My Assets, Requests) for `client_viewer` role users who lack `assets.create`
  - Assets filtered to the logged-in user's own employee record (matched by email)
  - "New Request" button opens the same request form as the full shell
- **Preview-as-client** — MSP admins can open any client's portal in a new tab using a short-lived token; endpoint at `GET /api/admin/preview-token/{tenant_id}`
- **Standalone mode** — `DEPLOYMENT_MODE=standalone` runs Tether as a single-company install with no MSP layer; the root domain is the tenant, no subdomain routing required
- Dockerfile added; `docker-compose.yml` includes MariaDB 11 service
- `audit.py` module for consistent audit log writes across all routers

### Changed
- Asset detail page now loads depreciation data inline with the asset fetch
- `GET /api/assets/activity` must be declared before `/{asset_id}` to avoid FastAPI route shadowing (same for all other specific sub-paths)

### Fixed
- `AuditLog` queries in the activity feed wrapped in `try/except Exception: pass` so older installs without the audit table continue to work
- Feb-29 leap-year edge case in `calculate_depreciation` end-of-life date calculation falls back to Mar 1

---

## [0.0.7] — 2026-06-07

### Added
- **Standalone deployment mode** (`DEPLOYMENT_MODE=standalone`) — single-company install without MSP layer; root domain is the tenant; seeded from `DEFAULT_TENANT_NAME`, `DEFAULT_TENANT_SLUG`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`
- `GET /api/public/branding` returns tenant branding for the login page (no auth required); standalone mode returns company branding at root domain
- `GET /api/public/demo` returns demo credentials when `DEPLOYMENT_MODE=demo`
- Sidebar "← All Clients" button for MSP admins navigating inside a client tenant
- `tests/test_admin.py` — admin endpoint and preview-token coverage
- `tests/test_public.py` — public branding and standalone branding tests
- `tests/test_standalone.py` — standalone mode seeding and login

### Changed
- README substantially expanded — full deployment guide, environment variable reference, DNS setup, database backend switching, backup/restore procedures, project structure

---

## [0.0.6] — 2026-06-06

### Fixed
- `test_employees.py` fixture compatibility fix

---

## [0.0.5] — 2026-06-06

### Changed
- CI: added missing `pip install httpx` step for pytest `TestClient`

---

## [0.0.4] — 2026-06-06

### Changed
- README rewritten with full Quick Start, Docker instructions, environment variable reference, DNS setup, database configuration, backup guide, and project structure tree

---

## [0.0.3] — 2026-06-05

### Added
- GitHub Actions CI workflow (`.github/workflows/ci.yml`) — runs pytest on push and pull request

---

## [0.0.2] — 2026-06-05

### Added
- Full test suite covering all existing routers:
  - `tests/conftest.py` — shared fixtures (TestClient, auth token, tenant, employee)
  - `tests/test_assets.py`, `test_auth.py`, `test_billing.py`, `test_dashboard.py`
  - `tests/test_admin.py`, `tests/test_employees.py`, `tests/test_locations.py`
  - `tests/test_password_reset.py`, `tests/test_public.py`, `tests/test_requests.py`
  - `tests/test_signup.py`, `tests/test_stripe.py`, `tests/test_tenants.py`, `tests/test_users.py`
- `pytest.ini` with `testpaths` and `asyncio_mode` settings

---

## [0.0.1] — 2026-06-03

### Added
- Initial application — core asset management platform
- **Asset tracking** — asset_tag, name, serial, model, manufacturer, status, purchase date/cost, warranty expiry, notes
- **Check-out / check-in** — assign assets to employees with full `CheckoutLog` history
- **Asset requests** — client users submit requests; MSP staff approve/decline with notes and status
- **Dashboard** — total assets, deployed count, total value, expiring warranties, status breakdown chart
- **QR labels** — per-asset QR codes (PNG download)
- **CSV import/export** — bulk asset upload; categories, locations, and employees created automatically on import
- **Search & filter** — keyword, status, category, location; sortable columns; pagination
- **Bulk operations** — bulk status update, bulk location change, bulk delete
- **Categories, locations, employees** — full CRUD with tenant scoping
- **Multi-tenant MSP** — each client gets a subdomain; `resolve_tenant_slug` middleware for subdomain routing
- **Role-based access control** — six built-in roles (`msp_admin`, `msp_technician`, `client_admin`, `client_manager`, `client_user`, `client_viewer`); per-user permission overrides
- **User management** — invite-based onboarding via email token; password reset via email token; change password
- **Email service** — `email_service.py` abstraction supporting `none`, `smtp`, `resend`, `sendgrid`
- **Warranty alerts** — scheduled email alerts for assets expiring within `WARRANTY_ALERT_DAYS`
- **Automated S3 backups** — scheduled backup to any S3-compatible storage
- **Rate limiting** — in-memory or Redis-backed on login, signup, and password-reset endpoints
- **Billing** — `MspBilling` model; Stripe webhook handler; tier-based asset limits (SaaS mode)
- **Demo mode** — `DEPLOYMENT_MODE=demo`; demo credentials endpoint; data-reset integration
- **Audit logging** (`AuditLog` model) — schema present from initial commit
- FastAPI backend, SQLAlchemy ORM, SQLite default / MariaDB / PostgreSQL
- Vanilla JS SPA frontend with Chart.js (vendored); no build step required
