from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Date, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base


# ── Tenant ────────────────────────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"
    id                 = Column(Integer, primary_key=True)
    name               = Column(String(120), nullable=False)
    slug               = Column(String(120), unique=True, nullable=False, index=True)
    logo_url           = Column(String(500), default="")
    accent_color       = Column(String(20), default="#d4f034")
    currency           = Column(String(10), default="USD")
    active             = Column(Boolean, default=True)
    created_at         = Column(DateTime, default=datetime.utcnow)
    email_from_name    = Column(String(120), nullable=True)
    email_from_address = Column(String(320), nullable=True)
    email_logo_url     = Column(String(500), nullable=True)
    email_accent_color = Column(String(20), nullable=True)
    asset_tag_prefix   = Column(String(20), nullable=True, default="")
    webhook_url        = Column(String(500), nullable=True)
    webhook_secret     = Column(String(120), nullable=True)

    users          = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    assets         = relationship("Asset", back_populates="tenant", cascade="all, delete-orphan")
    categories     = relationship("Category", back_populates="tenant", cascade="all, delete-orphan")
    locations      = relationship("Location", back_populates="tenant", cascade="all, delete-orphan")
    employees      = relationship("Employee", back_populates="tenant", cascade="all, delete-orphan")
    custom_domains = relationship("TenantDomain", back_populates="tenant", cascade="all, delete-orphan")


class MspBilling(Base):
    """One row per Tether installation."""
    __tablename__ = "msp_billing"
    id                     = Column(Integer, primary_key=True)
    tier                   = Column(String(32), default="trial")
    billing_interval       = Column(String(32), default="monthly")
    trial_ends_at          = Column(DateTime, nullable=True)
    billing_email          = Column(String(320), default="")
    msp_name               = Column(String(120), default="")
    notes                  = Column(String(1000), default="")
    stripe_customer_id     = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    stripe_price_id        = Column(String(255), nullable=True)
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class TenantDomain(Base):
    """Optional custom domains, e.g. assets.contosomsp.com → tenant"""
    __tablename__ = "tenant_domains"
    id         = Column(Integer, primary_key=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    domain     = Column(String(255), unique=True, nullable=False, index=True)
    verified   = Column(Boolean, default=False)
    tenant     = relationship("Tenant", back_populates="custom_domains")


# ── Permissions & Roles ───────────────────────────────────────────────────────

class Permission(Base):
    __tablename__ = "permissions"
    id   = Column(Integer, primary_key=True)
    key  = Column(String(100), unique=True, nullable=False)   # e.g. "assets.delete"
    description = Column(String(255), default="")
    role_permissions    = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")
    user_overrides      = relationship("UserPermissionOverride", back_populates="permission", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(80), unique=True, nullable=False)   # "msp_admin", "client_viewer" …
    description = Column(String(255), default="")
    is_msp_role = Column(Boolean, default=False)   # MSP staff roles vs client roles
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    users       = relationship("User", back_populates="role")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)
    id            = Column(Integer, primary_key=True)
    role_id       = Column(Integer, ForeignKey("roles.id"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False)
    role          = relationship("Role", back_populates="permissions")
    permission    = relationship("Permission", back_populates="role_permissions")


class UserPermissionOverride(Base):
    """Per-user grant or revoke on top of their role defaults."""
    __tablename__ = "user_permission_overrides"
    __table_args__ = (UniqueConstraint("user_id", "permission_id"),)
    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False)
    granted       = Column(Boolean, nullable=False)   # True = grant, False = revoke
    user          = relationship("User", back_populates="permission_overrides")
    permission    = relationship("Permission", back_populates="user_overrides")


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    tenant_id     = Column(Integer, ForeignKey("tenants.id"), nullable=True)   # NULL = MSP staff
    role_id       = Column(Integer, ForeignKey("roles.id"), nullable=False)
    name          = Column(String(120), nullable=False)
    email         = Column(String(320), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_msp_staff  = Column(Boolean, default=False)   # can access all tenants
    active        = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_login    = Column(DateTime, nullable=True)

    tenant               = relationship("Tenant", back_populates="users")
    role                 = relationship("Role", back_populates="users")
    permission_overrides = relationship("UserPermissionOverride", back_populates="user", cascade="all, delete-orphan")


# ── Per-tenant data (all scoped with tenant_id) ───────────────────────────────

class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)
    id        = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name      = Column(String(120), nullable=False)
    icon      = Column(String(64), default="box")
    assets    = relationship("Asset", back_populates="category")
    tenant    = relationship("Tenant", back_populates="categories")


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)
    id        = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name      = Column(String(120), nullable=False)
    address   = Column(String(255), default="")
    assets    = relationship("Asset", back_populates="location")
    tenant    = relationship("Tenant", back_populates="locations")


class Employee(Base):
    __tablename__ = "employees"
    id        = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name      = Column(String(120), nullable=False)
    email     = Column(String(320), default="")
    department = Column(String(120), default="")
    assets    = relationship("Asset", back_populates="assigned_to")
    tenant    = relationship("Tenant", back_populates="employees")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("tenant_id", "asset_tag"),)
    id            = Column(Integer, primary_key=True)
    tenant_id     = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    asset_tag     = Column(String(100), nullable=False, index=True)
    name          = Column(String(200), nullable=False)
    serial        = Column(String(120), default="")
    model         = Column(String(120), default="")
    manufacturer  = Column(String(120), default="")
    status        = Column(String(32), default="available")
    notes         = Column(Text, default="")
    purchase_date = Column(Date, nullable=True)
    purchase_cost = Column(Float, nullable=True)
    warranty_expiry = Column(Date, nullable=True)

    category_id   = Column(Integer, ForeignKey("categories.id"), nullable=True)
    location_id   = Column(Integer, ForeignKey("locations.id"), nullable=True)
    assigned_to_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    useful_life_years = Column(Integer, nullable=True)
    salvage_value     = Column(Float, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant        = relationship("Tenant", back_populates="assets")
    category      = relationship("Category", back_populates="assets")
    location      = relationship("Location", back_populates="assets")
    assigned_to   = relationship("Employee", back_populates="assets")
    history       = relationship("CheckoutLog", back_populates="asset", cascade="all, delete-orphan")
    notes_log     = relationship("AssetNote", back_populates="asset", cascade="all, delete-orphan",
                                 order_by="desc(AssetNote.created_at)")
    photos        = relationship("AssetPhoto", back_populates="asset", cascade="all, delete-orphan",
                                 order_by="desc(AssetPhoto.created_at)")
    maintenance_schedules = relationship("AssetMaintenance", back_populates="asset",
                                         cascade="all, delete-orphan",
                                         order_by="AssetMaintenance.due_date")


class CheckoutLog(Base):
    __tablename__ = "checkout_logs"
    id            = Column(Integer, primary_key=True)
    asset_id      = Column(Integer, ForeignKey("assets.id"), nullable=False)
    employee_id   = Column(Integer, ForeignKey("employees.id"), nullable=True)
    employee_name = Column(String(120), default="")
    action        = Column(String(32))
    note          = Column(String(500), default="")
    timestamp     = Column(DateTime, default=datetime.utcnow)
    asset         = relationship("Asset", back_populates="history")


# ── Software licences ─────────────────────────────────────────────────────────

class SoftwareLicence(Base):
    __tablename__ = "software_licences"
    id            = Column(Integer, primary_key=True)
    tenant_id     = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name          = Column(String(200), nullable=False)
    vendor        = Column(String(120), default="")
    licence_type  = Column(String(80), default="")
    total_seats   = Column(Integer, nullable=True)
    purchase_date = Column(Date, nullable=True)
    expiry_date   = Column(Date, nullable=True)
    purchase_cost = Column(Float, nullable=True)
    renewal_cost  = Column(Float, nullable=True)
    licence_key   = Column(Text, default="")
    notes         = Column(Text, default="")
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tenant        = relationship("Tenant")
    assignments   = relationship("LicenceAssignment", back_populates="licence",
                                 cascade="all, delete-orphan")


class LicenceAssignment(Base):
    __tablename__ = "licence_assignments"
    id          = Column(Integer, primary_key=True)
    licence_id  = Column(Integer, ForeignKey("software_licences.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    asset_id    = Column(Integer, ForeignKey("assets.id"), nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    notes       = Column(String(500), default="")
    licence     = relationship("SoftwareLicence", back_populates="assignments")
    employee    = relationship("Employee")
    asset       = relationship("Asset")


# ── Invite tokens ─────────────────────────────────────────────────────────────

class InviteToken(Base):
    __tablename__ = "invite_tokens"
    id         = Column(Integer, primary_key=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    role_id    = Column(Integer, ForeignKey("roles.id"), nullable=False)
    email      = Column(String(320), nullable=False)
    name       = Column(String(120), default="")
    used       = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    tenant     = relationship("Tenant")
    role       = relationship("Role")


# ── Asset requests (client self-service) ──────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id          = Column(Integer, primary_key=True)
    timestamp   = Column(DateTime, default=datetime.utcnow, index=True)
    actor_id    = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_email = Column(String(320), default="")
    actor_name  = Column(String(120), default="")
    tenant_id   = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    tenant_name = Column(String(120), default="")
    action      = Column(String(80), nullable=False, index=True)
    resource    = Column(String(80), default="")
    resource_id = Column(String(80), default="")
    detail      = Column(Text, default="")
    ip_address  = Column(String(64), default="")


# ── Custom fields ─────────────────────────────────────────────────────────────

class CustomFieldDef(Base):
    """Per-tenant field definition (label + type). MSP creates these."""
    __tablename__ = "custom_field_defs"
    __table_args__ = (UniqueConstraint("tenant_id", "label"),)
    id         = Column(Integer, primary_key=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    label      = Column(String(80), nullable=False)
    field_type = Column(String(20), default="text")   # text | number | date | boolean | url
    required   = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    tenant     = relationship("Tenant")
    values     = relationship("CustomFieldValue", back_populates="field_def",
                              cascade="all, delete-orphan")


class CustomFieldValue(Base):
    """Per-asset value for a custom field definition."""
    __tablename__ = "custom_field_values"
    __table_args__ = (UniqueConstraint("field_def_id", "asset_id"),)
    id           = Column(Integer, primary_key=True)
    field_def_id = Column(Integer, ForeignKey("custom_field_defs.id"), nullable=False, index=True)
    asset_id     = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    value        = Column(Text, default="")
    field_def    = relationship("CustomFieldDef", back_populates="values")
    asset        = relationship("Asset")


class UserTotp(Base):
    """TOTP secret for a user. One row per user; deleted when 2FA is disabled."""
    __tablename__ = "user_totp"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    secret     = Column(String(64), nullable=False)   # base32 secret (stored plaintext; DB at-rest encryption is operator responsibility)
    enabled    = Column(Boolean, default=False)        # False until first successful verify
    created_at = Column(DateTime, default=datetime.utcnow)
    user       = relationship("User")


class AssetCheckinToken(Base):
    """Single-use token for a public (unauthenticated) asset check-in."""
    __tablename__ = "asset_checkin_tokens"
    id         = Column(Integer, primary_key=True)
    token      = Column(String(64), unique=True, nullable=False, index=True)
    asset_id   = Column(Integer, ForeignKey("assets.id"), nullable=False)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at    = Column(DateTime, nullable=True)
    asset      = relationship("Asset")


class AssetNote(Base):
    """Append-only timestamped note on an asset."""
    __tablename__ = "asset_notes"
    id         = Column(Integer, primary_key=True)
    asset_id   = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    author_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    author_name = Column(String(120), default="")
    body       = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    asset      = relationship("Asset", back_populates="notes_log")
    author     = relationship("User")


class SavedFilter(Base):
    """Named asset filter set, scoped per user and tenant."""
    __tablename__ = "saved_filters"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    name       = Column(String(120), nullable=False)
    filters    = Column(Text, default="{}")   # JSON blob: {q, status, category_id, location_id, department}
    created_at = Column(DateTime, default=datetime.utcnow)
    user       = relationship("User")


class AssetMaintenance(Base):
    __tablename__ = "asset_maintenance"
    id            = Column(Integer, primary_key=True)
    asset_id      = Column(Integer, ForeignKey("assets.id"), nullable=False)
    tenant_id     = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    title         = Column(String(200), nullable=False)
    maintenance_type = Column(String(80), default="")
    due_date      = Column(Date, nullable=False)
    assigned_to_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    notes         = Column(Text, default="")
    status        = Column(String(32), default="scheduled")  # scheduled | done | overdue
    completed_at  = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    asset         = relationship("Asset", back_populates="maintenance_schedules")
    assigned_to   = relationship("Employee")


class AssetPhoto(Base):
    __tablename__ = "asset_photos"
    id         = Column(Integer, primary_key=True)
    asset_id   = Column(Integer, ForeignKey("assets.id"), nullable=False)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    filename   = Column(String(260), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    asset      = relationship("Asset", back_populates="photos")


class AssetRequest(Base):
    __tablename__ = "asset_requests"
    id          = Column(Integer, primary_key=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    requested_by_name = Column(String(120), default="")
    title       = Column(String(200), nullable=False)
    description = Column(Text, default="")
    priority    = Column(String(20), default="normal")   # low / normal / high / urgent
    status      = Column(String(20), default="open")     # open / in_progress / fulfilled / declined
    notes       = Column(Text, default="")           # MSP response notes
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tenant      = relationship("Tenant")
