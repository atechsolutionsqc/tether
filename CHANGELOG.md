# Changelog

All notable changes to Tether are documented here.  
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Security
- **Cross-tenant employee write access blocked** *(CRITICAL)* — `PUT /api/employees/{id}` and `DELETE /api/employees/{id}` were missing the `tenant_id` isolation check, allowing any authenticated user to modify or delete employees from any tenant. Both endpoints now return 404 for resources outside the requesting tenant.
- **Cross-tenant saved-filter delete blocked** *(MEDIUM)* — `DELETE /api/saved-filters/{id}` checked `user_id` but not `tenant_id`, allowing a user to delete filters belonging to the same user ID on a different tenant. The endpoint now enforces both checks.
- **Custom field values scoped to tenant** *(MEDIUM)* — `get_custom_field_values()` helper now filters out field definitions that do not belong to the requesting tenant, preventing data from one tenant's custom fields from appearing in another tenant's asset responses. All three call sites (`GET /custom-fields/values/{id}`, `PUT /custom-fields/values/{id}`, asset detail) pass `tenant_id` explicitly.
- **10 cross-tenant isolation tests added** — `tests/test_tenant_isolation.py` covers employee update/delete, saved-filter delete, and custom-field read/write across two isolated tenants.
- **Invite tokens hashed** — invite tokens are now stored as SHA-256 hashes in the database. A DB leak no longer exposes usable invite links. Existing plaintext `token` column is migrated to `token_hash` automatically on startup.
- **Password reset endpoint hardened** — `GET /api/auth/reset-password/{token}` no longer returns the user's name and email in the response, preventing information disclosure if a token is intercepted.
- **Default password warning** — startup now logs a loud warning if `ADMIN_PASSWORD` is still set to the default value `admin` (outside of demo mode).
- **Multi-worker rate limit warning** — startup now logs a warning if more than one worker is detected without Redis configured, as in-memory rate limiting is per-process and can be bypassed across workers.

### Fixed
- **Duplicate backup loop** — `main.py` lifespan was starting a second `backup_loop()` task in addition to the one already managed by `scheduler.py`. Removed the duplicate; `scheduler.py` is now the sole owner of the backup loop.
- **Hardcoded version** — `GET /api/admin/status` and `GET /api/health` now read the version from the FastAPI app object (`app.version`) instead of a hardcoded `"1.0.0"` string.
- **Preview token wrong role** — the MSP tenant-preview user is now created with the `client_admin` role (falling back to the first non-MSP role if `client_admin` doesn't exist), instead of whatever non-MSP role happened to appear first in the DB (often `client_viewer`).
- **Activity feed pagination correctness** — `GET /api/assets/activity` now counts `total` from the database (separate `COUNT` queries on `CheckoutLog` and `AuditLog`) and fetches only a bounded window of rows from each source before merging, so pagination and totals are correct at scale rather than loading all rows into Python first.
- **Schema migrations** — `init_db()` now runs `ALTER TABLE … ADD COLUMN IF NOT EXISTS` for every column added after the initial release. Existing MariaDB/PostgreSQL installs that pre-date a model change will have the missing columns added automatically on the next startup rather than crashing with `Unknown column` errors. SQLite uses a `try/except` fallback (no `IF NOT EXISTS` support). Covers the `email_from_*` columns on `tenants` and `useful_life_years`/`salvage_value` on `assets`.

### Added
### Changed / Improved
- **Pagination on employees, categories, locations** — `GET /api/employees`, `/api/categories`, `/api/locations` now return `{items, total, limit, offset}` (default limit 200, max 1000); `q` search param added to employees. Frontend and all tests updated.
- **Structured logging** — set `LOG_FORMAT=json` to emit machine-readable JSON log lines (`ts`, `level`, `logger`, `msg`); defaults to text. `RequestLoggingMiddleware` emits one access-log entry per request (JSON in json mode, debug-level text otherwise).
- **Preview user cleanup** — `__preview@*` users older than 24 h are deleted daily at 03:00 UTC by the scheduler, preventing unbounded accumulation.

### Added
- **Webhook outbound events** — per-tenant webhook for PSA/integration use
  - Configure `webhook_url` and `webhook_secret` in tenant settings (UI + API)
  - Events fired: `asset.created`, `asset.updated`, `asset.deleted`, `request.status_changed`, `warranty.expiring`
  - Each POST is signed with HMAC-SHA256: `X-Tether-Signature: sha256=<hex>` using the tenant's secret
  - Up to 3 retries with exponential back-off; failures are logged but never block the main request
  - `webhook_service.py` — standalone delivery module with no external dependencies
  - 8 tests (settings save/clear, fire no-op, signed POST, graceful failure, asset create fires webhook)
- **Asset maintenance scheduling** — schedule and track maintenance tasks per asset
  - `POST /api/assets/{id}/maintenance` — create a scheduled maintenance task (title, type, due date, assignee, notes)
  - `GET /api/assets/{id}/maintenance` — list maintenance tasks; auto-marks overdue tasks on each read
  - `PATCH /api/assets/{id}/maintenance/{mid}/complete` — mark complete
  - `DELETE /api/assets/{id}/maintenance/{mid}` — delete
  - Dashboard now shows overdue maintenance count badge and upcoming maintenance panel
  - Scheduler sends daily reminder emails at 07:00 UTC for tasks due within 3 days (configurable via `MAINTENANCE_ALERT_DAYS`; disable with `MAINTENANCE_ALERTS_ENABLED=false`)
  - 6 tests (create, list, complete, overdue auto-status, delete, auth) + dashboard shape updated
- **Asset photo upload** — attach photos to assets
  - `POST /api/assets/{id}/photos` — multipart upload (JPEG, PNG, GIF, WebP, max 10 MB); photos stored in `data/uploads/` and served at `/uploads/<filename>`
  - `GET /api/assets/{id}/photos` — list photos with URL and timestamp
  - `DELETE /api/assets/{id}/photos/{photo_id}` — delete photo and file
  - Photos panel added to asset detail page with thumbnail grid and delete buttons
  - 5 tests (upload, list, delete, file-type rejection, auth)
- **Keyboard shortcuts** — global keyboard handler: `n` opens the new asset form, `/` focuses search, `?` shows a shortcut help overlay, `Esc` closes any open dialog; "Shortcuts" button added to sidebar footer
- **Activity feed date range filter** — `GET /api/assets/activity` now accepts `date_from` and `date_to` query params (ISO 8601 date strings); date pickers added to the Activity Feed toolbar in the frontend; 4 tests (excludes older/future events, includes today, invalid date ignored gracefully)
- **Depreciation schedule export** — year-by-year book value breakdown per asset
  - `GET /api/reports/depreciation/schedule/{id}` — JSON schedule with year, year_end, annual depreciation, accumulated depreciation, book value
  - `GET /api/reports/depreciation/schedule/{id}/export` — CSV download of the same data
  - "Schedule" download button added to the Depreciation panel on the asset detail page
  - 5 tests (correct row count, decreasing book value, CSV export, 404, auth)
- **Public asset check-in page** — generate a single-use, 7-day link per asset that lets an employee self-check-in without logging in
  - `POST /api/assets/{id}/checkin-token` — generates (and invalidates any previous unused) check-in token; requires `assets.edit`
  - `GET /api/assets/public/checkin/{token}` — shows asset info (no auth)
  - `POST /api/assets/public/checkin/{token}` — checks the asset in, marks token used; returns 410 if already used or expired
  - "Self-service link" button in the QR Label panel on the asset detail page; modal shows the URL with a Copy button
  - `/checkin/<token>` frontend route shows a branded confirmation screen
  - 5 tests (token generation, info fetch, used/expired enforcement, auth)
- **Tenant onboarding wizard** — 3-step setup modal appears automatically after creating a new client tenant
  - Step 1: invite the first user (sends an invite email; skippable)
  - Step 2: add extra asset categories beyond the defaults (skippable)
  - Step 3: completion screen with a "Open Client Portal" shortcut
  - Progress indicators shown at the top of each step
- **Asset notes history** — append-only timestamped notes log on each asset; notes show author name, date, and a delete button; replaces the single-overwrite notes field for structured history
  - `GET /api/assets/{id}/notes` — list notes (newest first)
  - `POST /api/assets/{id}/notes` — append a note (requires `assets.edit`)
  - `DELETE /api/assets/{id}/notes/{note_id}` — delete a note (requires `assets.edit`, tenant-scoped)
  - Notes panel on asset detail page with add-note textarea and delete buttons
  - 6 tests (CRUD, cross-tenant isolation, auth)
- **Saved search / filters** — save the current asset list filter combination as a named view; re-apply it from a dropdown in one click; per-user scoped; deletable
  - `GET /api/saved-filters` — list this user's saved views for the current tenant
  - `POST /api/saved-filters` — create a named view with `{name, filters}` payload
  - `DELETE /api/saved-filters/{id}` — delete own filter (404 if not owner)
  - "Save View" button in asset toolbar + "Saved views…" dropdown when any views exist
  - 5 tests (CRUD, user scoping, auth)
- **Tenant-level user groups / departments** — department filter on the asset list; departments endpoint for dropdown population
  - `GET /api/employees/departments` — distinct non-empty department values for the tenant
  - `GET /api/assets?department=Engineering` — filters to assets assigned to people in that department
  - Asset list shows a Department dropdown when any employees have departments set
  - 5 tests (distinct values, empty exclusion, asset filter, auth)
- **Asset age report** — new Reports sub-page showing assets by age bracket (0–1yr, 1–3yr, 3–5yr, 5yr+) with expandable asset lists per bracket and CSV export
  - `GET /api/reports/age` — returns bracket counts and asset details
  - `GET /api/reports/age/export` — CSV with asset_tag, name, purchase_date, age_years, bracket, status, category, tenant
  - 4 tests
- **Per-tenant asset tag prefix** — configure a prefix (e.g. `ACME-`) in Settings; new asset form pre-populates the tag field with the prefix; prefix is uppercased and stored on the tenant; 4 tests
- **Bulk reassign employee** — when an employee still has assets, a "Reassign" button (shuffle icon) appears; opens a modal to bulk-move all their assets to another person or set to unassigned/available before deletion
  - `POST /api/employees/{id}/reassign` — moves all assets to `to_employee_id` (or unassigns if `null`); 5 tests including cross-tenant isolation
  - Delete endpoint error message now hints at the reassign endpoint
- **Dark mode** — CSS variable-based dark/light toggle in the sidebar footer; state persisted in `localStorage`; all main-content surfaces (`--bg`, `--surface`, `--border`, `--text` family) respond to the `data-theme="dark"` attribute on `<html>`
- **Bulk import preview/diff** — CSV import now has a two-step flow: click **Preview** to see exactly what would be created, updated, or rejected before anything is written; click **Confirm Import** to commit
  - `POST /api/assets/import/csv/preview` — returns `{creates, updates, errors, new_cf_defs, summary}` without touching the DB; each update row lists which fields would change and their before/after values
  - New custom-field columns are flagged in the preview so users know new field definitions will be auto-created
  - 7 tests (create detection, update detection with diff, error reporting, no-commit guarantee, auth)
- **Asset assignment history on employee profile** — click any person in the People list (or the new clock icon) to open a history modal showing all assets ever checked out to them, with action, date, and a "Current" badge for still-assigned items; clicking an asset tag navigates directly to that asset
  - `GET /api/employees/{id}/history` — returns `{employee, history[]}` with `currently_assigned` flag; fully tenant-scoped; 5 tests
- **Licence expiry email alerts** — daily scheduler job that emails MSP admins about software licences expiring within a configurable window
  - Runs daily at 09:00 UTC (offset from warranty alerts)
  - Configurable via `LICENCE_ALERTS_ENABLED` (default `true`) and `LICENCE_ALERT_DAYS` (default 30)
  - `POST /api/admin/alerts/licence` — manual trigger (MSP admin only)
  - `/api/admin/status` now includes `licence_alerts` and `licence_window_days` in the services section
  - 3 tests
- **MSP dashboard per-client drill-down** — click any client row in the MSP dashboard to expand an inline panel with full tenant stats (assets, value, expiring warranties, recent activity) without navigating away; quick-action buttons to "Open as client" (preview token) or "Switch to tenant"
  - `GET /api/dashboard/client/{tenant_id}` — full tenant stats for MSP staff (requires `msp.dashboard`); 4 tests
- **Asset label/tag printing** — select assets in bulk and print QR label stickers
  - `POST /api/assets/labels` — returns a print-ready HTML page with QR codes for selected assets; three size options (small/4×4, medium/3×3, large/2×2 per row)
  - Labels include asset tag and name; browser print dialog or "Save as PDF" produces the final output (no server-side PDF dependency)
  - "Print Labels" button added to the bulk-select toolbar in the asset list
  - 6 tests including cross-tenant isolation
- **Two-factor authentication (TOTP)** — optional authenticator-app 2FA for MSP accounts
  - `UserTotp` model stores a per-user TOTP secret; table created automatically on startup
  - `POST /api/auth/totp/setup` — generate secret + QR code SVG (ready to scan in any TOTP app)
  - `POST /api/auth/totp/verify` — confirm first code to activate 2FA
  - `GET  /api/auth/totp/status` — returns `{enabled: true/false}`
  - `DELETE /api/auth/totp` — disable 2FA; requires current password
  - Login flow: when 2FA is active, `/api/auth/login` returns `{totp_required: true, totp_token: "..."}` (5-minute challenge token, not a session); `POST /api/auth/totp/authenticate` exchanges it + code for the full JWT
  - Rate limited: 10 bad TOTP codes per IP per 5 minutes
  - Client users cannot enable 2FA (MSP accounts only)
  - Settings page TOTP panel: scan QR, verify code, disable with password confirmation
  - Login page intercepts the TOTP challenge and shows a code-entry screen before completing login
  - 13 tests in `tests/test_totp.py`
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
