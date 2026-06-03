from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# ── Auth ──────────────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PasswordChange(BaseModel):
    current_password: str
    new_password: str


# ── Tenant ────────────────────────────────────────────────────────────────────
class TenantIn(BaseModel):
    name: str
    slug: str
    logo_url: str = ""
    accent_color: str = "#d4f034"
    currency: str = "USD"

class TenantOut(TenantIn):
    id: int
    active: bool
    created_at: Optional[datetime]
    asset_count: int = 0
    user_count: int = 0
    class Config:
        from_attributes = True


# ── Users ─────────────────────────────────────────────────────────────────────
class UserIn(BaseModel):
    name: str
    email: str
    password: Optional[str] = None
    role_id: int
    tenant_id: Optional[int] = None
    is_msp_staff: bool = False
    active: bool = True

class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role_id: int
    role_name: Optional[str] = None
    tenant_id: Optional[int]
    tenant_name: Optional[str] = None
    is_msp_staff: bool
    active: bool
    created_at: Optional[datetime]
    class Config:
        from_attributes = True

class UserPermOverride(BaseModel):
    permission_key: str
    granted: bool


# ── Roles ─────────────────────────────────────────────────────────────────────
class RoleOut(BaseModel):
    id: int
    name: str
    description: str
    is_msp_role: bool
    permissions: List[str] = []
    class Config:
        from_attributes = True


# ── Category ──────────────────────────────────────────────────────────────────
class CategoryIn(BaseModel):
    name: str
    icon: str = "box"

class CategoryOut(CategoryIn):
    id: int
    asset_count: int = 0
    class Config:
        from_attributes = True


# ── Location ──────────────────────────────────────────────────────────────────
class LocationIn(BaseModel):
    name: str
    address: str = ""

class LocationOut(LocationIn):
    id: int
    asset_count: int = 0
    class Config:
        from_attributes = True


# ── Employee ──────────────────────────────────────────────────────────────────
class EmployeeIn(BaseModel):
    name: str
    email: str = ""
    department: str = ""

class EmployeeOut(EmployeeIn):
    id: int
    asset_count: int = 0
    class Config:
        from_attributes = True


# ── Asset ─────────────────────────────────────────────────────────────────────
class AssetIn(BaseModel):
    asset_tag: str
    name: str
    serial: str = ""
    model: str = ""
    manufacturer: str = ""
    status: str = "available"
    notes: str = ""
    purchase_date: Optional[date] = None
    purchase_cost: Optional[float] = None
    warranty_expiry: Optional[date] = None
    category_id: Optional[int] = None
    location_id: Optional[int] = None
    assigned_to_id: Optional[int] = None

class AssetOut(AssetIn):
    id: int
    tenant_id: int
    category_name: Optional[str] = None
    location_name: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class CheckoutIn(BaseModel):
    employee_id: Optional[int] = None
    note: str = ""

class HistoryOut(BaseModel):
    id: int
    action: str
    employee_name: str
    note: str
    timestamp: datetime
    class Config:
        from_attributes = True


# ── Settings ──────────────────────────────────────────────────────────────────
class SettingsIn(BaseModel):
    name: str
    currency: str
    logo_url: str = ""
    accent_color: str = "#d4f034"
