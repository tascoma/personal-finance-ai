import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

# bcrypt only consumes the first 72 bytes of a password and raises on longer
# input, so bound the password here rather than letting it 500 at the hash call.
_BCRYPT_MAX_BYTES = 72


def _validate_password_bounds(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(v.encode()) > _BCRYPT_MAX_BYTES:
        raise ValueError("Password must be at most 72 bytes")
    return v


class UserRegister(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_bounds(cls, v: str) -> str:
        return _validate_password_bounds(v)


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_max_bytes(cls, v: str) -> str:
        # Bound login input too so an over-long password can't error inside bcrypt.
        if len(v.encode()) > _BCRYPT_MAX_BYTES:
            raise ValueError("Password must be at most 72 bytes")
        return v


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
