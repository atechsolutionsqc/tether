from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Date, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base


# ── Tenant ────────────────────────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"
    id            = Column(Integer, primary_key=True)
    name          = Column(String, nullable=False)
    slug          = Column(String, unique=True, nullable=False, index=True)
    logo_url      = Column(String, default="")
    accent_color  = Column(String, default="#d4f034")
    currency      = Column(String, default="USD")
    active        = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

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
    tier                   = Column(String, default="trial")
    billing_interval       = Column(String, default="monthly")
    trial_ends_at          = Column(DateTime, nullable=True)
    billing_email          = Column(String, default="")
    msp_name               = Column(String, default="")
    notes                  = Column(String, default="")
    stripe_customer_id     = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    stripe_price_id        = Column(String, nullable=True)
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class TenantDomain(Base):
    """Optional custom domains, e.g. assets.contosomsp.com → tenant"""
    __tablename__ = "tenant_domains"
    id         = Column(Integer, primary_key=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    domain     = Column(String, unique=True, nullable=False, index=True)
    verified   = Column(Boolean, default=False)
    tenant     = relationship("Tenant", back_populates="custom_domains")


# ── Permissions & Roles ───────────────────────────────────────────────────────

class Permission(Base):
    __tablename__ = "permissions"
    id   = Column(Integer, primary_key=True)
    key  = Column(String, unique=True, nullable=False)   # e.g. "assets.delete"
    description = Column(String, default="")
    role_permissions    = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")
    user_overrides      = relationship("UserPermissionOverride", back_populates="permission", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    id          = Column(Integer, primary_key=True)
    name        = Column(String, unique=True, nullable=False)   # "msp_admin", "client_viewer" …
    description = Column(String, default="")
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
    name          = Column(String, nullable=False)
    email         = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
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
    name      = Column(String, nullable=False)
    icon      = Column(String, default="box")
    assets    = relationship("Asset", back_populates="category")
    tenant    = relationship("Tenant", back_populates="categories")


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)
    id        = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name      = Column(String, nullable=False)
    address   = Column(String, default="")
    assets    = relationship("Asset", back_populates="location")
    tenant    = relationship("Tenant", back_populates="locations")


class Employee(Base):
    __tablename__ = "employees"
    id        = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name      = Column(String, nullable=False)
    email     = Column(String, default="")
    department = Column(String, default="")
    assets    = relationship("Asset", back_populates="assigned_to")
    tenant    = relationship("Tenant", back_populates="employees")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("tenant_id", "asset_tag"),)
    id            = Column(Integer, primary_key=True)
    tenant_id     = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    asset_tag     = Column(String, nullable=False, index=True)
    name          = Column(String, nullable=False)
    serial        = Column(String, default="")
    model         = Column(String, default="")
    manufacturer  = Column(String, default="")
    status        = Column(String, default="available")
    notes         = Column(Text, default="")
    purchase_date = Column(Date, nullable=True)
    purchase_cost = Column(Float, nullable=True)
    warranty_expiry = Column(Date, nullable=True)

    category_id   = Column(Integer, ForeignKey("categories.id"), nullable=True)
    location_id   = Column(Integer, ForeignKey("locations.id"), nullable=True)
    assigned_to_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant        = relationship("Tenant", back_populates="assets")
    category      = relationship("Category", back_populates="assets")
    location      = relationship("Location", back_populates="assets")
    assigned_to   = relationship("Employee", back_populates="assets")
    history       = relationship("CheckoutLog", back_populates="asset", cascade="all, delete-orphan")


class CheckoutLog(Base):
    __tablename__ = "checkout_logs"
    id            = Column(Integer, primary_key=True)
    asset_id      = Column(Integer, ForeignKey("assets.id"), nullable=False)
    employee_id   = Column(Integer, ForeignKey("employees.id"), nullable=True)
    employee_name = Column(String, default="")
    action        = Column(String)
    note          = Column(String, default="")
    timestamp     = Column(DateTime, default=datetime.utcnow)
    asset         = relationship("Asset", back_populates="history")


# ── Invite tokens ─────────────────────────────────────────────────────────────

class InviteToken(Base):
    __tablename__ = "invite_tokens"
    id         = Column(Integer, primary_key=True)
    token      = Column(String, unique=True, nullable=False, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    role_id    = Column(Integer, ForeignKey("roles.id"), nullable=False)
    email      = Column(String, nullable=False)
    name       = Column(String, default="")
    used       = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    tenant     = relationship("Tenant")
    role       = relationship("Role")


# ── Asset requests (client self-service) ──────────────────────────────────────

class AssetRequest(Base):
    __tablename__ = "asset_requests"
    id          = Column(Integer, primary_key=True)
    tenant_id   = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    requested_by_name = Column(String, default="")
    title       = Column(String, nullable=False)
    description = Column(Text, default="")
    priority    = Column(String, default="normal")   # low / normal / high / urgent
    status      = Column(String, default="open")     # open / in_progress / fulfilled / declined
    notes       = Column(Text, default="")           # MSP response notes
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tenant      = relationship("Tenant")
