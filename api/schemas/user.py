from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime


class UserCreate(BaseModel):
    username: str
    password: str
    role: Literal["admin", "driver"] = "driver"


class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[Literal["admin", "driver"]] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
