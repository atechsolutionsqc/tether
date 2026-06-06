from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., max_length=128)


# ── Tenant ────────────────────────────────────────────────────────────────────
class TenantIn(BaseModel):
    name: str         = Field(..., min_length=1, max_length=120)
    slug: str         = Field(..., min_length=1, max_length=60)
    logo_url: str     = Field("", max_length=500)
    accent_color: str = Field("#d4f034", max_length=20)
    currency: str     = Field("USD", max_length=10)

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
    name: str                   = Field(..., min_length=1, max_length=120)
    email: str                  = Field(..., max_length=254)
    password: Optional[str]     = Field(None, max_length=128)
    role_id: int
    tenant_id: Optional[int]    = None
    is_msp_staff: bool          = False
    active: bool                = True

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
    permission_key: str = Field(..., max_length=80)
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
    name: str     = Field(..., min_length=1, max_length=80)
    icon: str     = Field("box", max_length=40)

class CategoryOut(CategoryIn):
    id: int
    asset_count: int = 0
    class Config:
        from_attributes = True


# ── Location ──────────────────────────────────────────────────────────────────
class LocationIn(BaseModel):
    name: str    = Field(..., min_length=1, max_length=120)
    address: str = Field("", max_length=300)

class LocationOut(LocationIn):
    id: int
    asset_count: int = 0
    class Config:
        from_attributes = True


# ── Employee ──────────────────────────────────────────────────────────────────
class EmployeeIn(BaseModel):
    name: str       = Field(..., min_length=1, max_length=120)
    email: str      = Field("", max_length=254)
    department: str = Field("", max_length=80)

class EmployeeOut(EmployeeIn):
    id: int
    asset_count: int = 0
    class Config:
        from_attributes = True


# ── Asset ─────────────────────────────────────────────────────────────────────
class AssetIn(BaseModel):
    asset_tag:       str            = Field(..., min_length=1, max_length=100)
    name:            str            = Field(..., min_length=1, max_length=200)
    serial:          str            = Field("", max_length=100)
    model:           str            = Field("", max_length=100)
    manufacturer:    str            = Field("", max_length=100)
    status:          str            = Field("available", max_length=40)
    notes:           str            = Field("", max_length=2000)
    purchase_date:   Optional[date] = None
    purchase_cost:   Optional[float] = None
    warranty_expiry: Optional[date] = None
    category_id:     Optional[int]  = None
    location_id:     Optional[int]  = None
    assigned_to_id:  Optional[int]  = None

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
    note: str = Field("", max_length=500)

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
    name:         str = Field(..., min_length=1, max_length=120)
    currency:     str = Field(..., max_length=10)
    logo_url:     str = Field("", max_length=500)
    accent_color: str = Field("#d4f034", max_length=20)
