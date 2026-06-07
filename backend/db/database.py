import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# ── Database URL resolution ────────────────────────────────────────────────────
# Priority:
#   1. DATABASE_URL env var (explicit, any supported DB)
#   2. MariaDB/MySQL via individual env vars (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD)
#   3. SQLite fallback — zero-config, file lives in TETHER_DATA directory

DATA_DIR = os.environ.get("TETHER_DATA", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
os.makedirs(DATA_DIR, exist_ok=True)

def _build_database_url() -> str:
    # Explicit DATABASE_URL wins
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    # MariaDB/MySQL via individual vars
    db_host = os.environ.get("DB_HOST")
    db_port = os.environ.get("DB_PORT", "3306")
    db_name = os.environ.get("DB_NAME", "tether")
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASSWORD", "")

    if db_host and db_user:
        return f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}?charset=utf8mb4"

    # SQLite fallback
    return f"sqlite:///{os.path.join(DATA_DIR, 'tether.db')}"

DATABASE_URL = _build_database_url()
_is_sqlite   = DATABASE_URL.startswith("sqlite")
_is_mysql    = DATABASE_URL.startswith("mysql")
_is_postgres = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")

_engine_kwargs = {}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
if _is_mysql:
    # Keep connections alive; MariaDB closes idle connections after wait_timeout
    _engine_kwargs["pool_recycle"]  = 3600
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"]     = 10
    _engine_kwargs["max_overflow"]  = 20

if _is_postgres:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"]     = 10
    _engine_kwargs["max_overflow"]  = 20

engine = create_engine(DATABASE_URL, **_engine_kwargs)

# Enforce foreign keys for SQLite (off by default)
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Permission catalogue ───────────────────────────────────────────────────────
ALL_PERMISSIONS = [
    ("assets.view",       "View assets"),
    ("assets.create",     "Create assets"),
    ("assets.edit",       "Edit assets"),
    ("assets.delete",     "Delete assets"),
    ("assets.checkout",   "Check out assets"),
    ("assets.checkin",    "Check in assets"),
    ("assets.import",     "Import assets via CSV"),
    ("assets.export",     "Export assets to CSV"),
    ("categories.manage", "Manage categories"),
    ("locations.manage",  "Manage locations"),
    ("employees.manage",  "Manage people"),
    ("users.manage",      "Manage users in their tenant"),
    ("reports.view",      "View reports"),
    ("settings.manage",   "Manage tenant settings"),
    ("tenants.manage",    "Create/edit/delete tenants (MSP only)"),
    ("msp.dashboard",     "Access the MSP cross-client dashboard"),
    ("msp.impersonate",   "Jump into any client tenant"),
]

# role_name → (is_msp_role, [permission_keys])
DEFAULT_ROLES = {
    "msp_admin": (True, [p[0] for p in ALL_PERMISSIONS]),
    "msp_technician": (True, [
        "assets.view","assets.create","assets.edit","assets.checkout","assets.checkin",
        "assets.import","assets.export","categories.manage","locations.manage",
        "employees.manage","reports.view","msp.dashboard",
    ]),
    "client_admin": (False, [
        "assets.view","assets.create","assets.edit","assets.delete",
        "assets.checkout","assets.checkin","assets.import","assets.export",
        "categories.manage","locations.manage","employees.manage",
        "users.manage","reports.view","settings.manage",
    ]),
    "client_manager": (False, [
        "assets.view","assets.create","assets.edit",
        "assets.checkout","assets.checkin","assets.export",
        "categories.manage","locations.manage","employees.manage","reports.view",
    ]),
    "client_viewer": (False, [
        "assets.view","assets.export","reports.view",
    ]),
}


def init_db():
    from models import models  # noqa: F401
    # Ensure all model tables including password reset tokens are registered
    from routers.password_reset import PasswordResetToken  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _seed(SessionLocal())


def _seed(db):
    from models.models import Permission, Role, RolePermission, User, Tenant, Category, Location, MspBilling
    from security import hash_password

    deployment_mode = os.environ.get("DEPLOYMENT_MODE", "selfhosted")
    standalone = deployment_mode == "standalone"

    # 1. Permissions
    perm_map = {}
    for key, desc in ALL_PERMISSIONS:
        p = db.query(Permission).filter(Permission.key == key).first()
        if not p:
            p = Permission(key=key, description=desc)
            db.add(p)
            db.flush()
        perm_map[key] = p

    # 2. Roles
    role_map = {}
    for rname, (is_msp, pkeys) in DEFAULT_ROLES.items():
        r = db.query(Role).filter(Role.name == rname).first()
        if not r:
            r = Role(name=rname, is_msp_role=is_msp,
                     description=rname.replace("_", " ").title())
            db.add(r)
            db.flush()
        # sync permissions
        existing = {rp.permission_id for rp in r.permissions}
        for pk in pkeys:
            pid = perm_map[pk].id
            if pid not in existing:
                db.add(RolePermission(role_id=r.id, permission_id=pid))
        role_map[rname] = r

    # 3. Default tenant (skipped if any tenant already exists)
    if not db.query(Tenant).first():
        default_slug = os.environ.get("DEFAULT_TENANT_SLUG", "mycompany" if standalone else "demo")
        default_name = os.environ.get("DEFAULT_TENANT_NAME", "My Company"  if standalone else "Demo Client")
        t = Tenant(name=default_name, slug=default_slug, currency="USD")
        db.add(t)
        db.flush()
        for cname, cicon in [("Laptop","laptop"),("Desktop","monitor"),("Monitor","tv"),
                              ("Phone","smartphone"),("Server","server"),
                              ("Network","wifi"),("Peripheral","mouse")]:
            db.add(Category(tenant_id=t.id, name=cname, icon=cicon))
        for lname in ["Head Office", "Warehouse", "Remote"]:
            db.add(Location(tenant_id=t.id, name=lname))

    # 4. Admin user — MSP admin in normal modes; client_admin in standalone
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@usetether.ca")
    admin_pass  = os.environ.get("ADMIN_PASSWORD", "admin")
    admin_name  = os.environ.get("ADMIN_NAME", "Admin" if standalone else "MSP Admin")

    if standalone:
        # Seed a client_admin for the default tenant if none exists yet
        default_tenant = db.query(Tenant).first()
        if default_tenant and not db.query(User).filter(
            User.tenant_id == default_tenant.id,
            User.is_msp_staff == False,  # noqa: E712
        ).first():
            db.add(User(
                tenant_id=default_tenant.id,
                role_id=role_map["client_admin"].id,
                name=admin_name,
                email=admin_email,
                password_hash=hash_password(admin_pass),
                is_msp_staff=False,
            ))
    else:
        # MSP / SaaS / demo: seed MSP admin
        if not db.query(User).filter(User.is_msp_staff == True).first():  # noqa: E712
            db.add(User(
                tenant_id=None,
                role_id=role_map["msp_admin"].id,
                name=admin_name,
                email=admin_email,
                password_hash=hash_password(admin_pass),
                is_msp_staff=True,
            ))

    # 5. Billing row (one per installation; skipped in standalone)
    if not standalone:
        from billing import is_saas, DEPLOYMENT_MODE
        from datetime import datetime, timedelta
        if not db.query(MspBilling).first():
            tier = "trial" if is_saas() else "selfhosted"
            trial_ends = datetime.utcnow() + timedelta(days=30) if tier == "trial" else None
            db.add(MspBilling(tier=tier, trial_ends_at=trial_ends))

    db.commit()
    db.close()
