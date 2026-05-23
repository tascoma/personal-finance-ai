import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class UserRegister(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    user_id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DeviceTokenRegister(BaseModel):
    apns_token: str
    bundle_id: str

    @field_validator("apns_token")
    @classmethod
    def token_not_empty(cls, v: str) -> str:
        if not v or len(v) < 16:
            raise ValueError("apns_token looks invalid")
        return v


class DeviceTokenRead(BaseModel):
    id: uuid.UUID
    bundle_id: str
    created_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}
