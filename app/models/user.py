"""
User model — Pydantic schemas and DB helpers.

Roles: "applicant" | "reviewer"
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserInDB(BaseModel):
    """Full user document as stored in MongoDB."""
    id: Optional[str] = Field(None, alias="_id")
    email: str
    password_hash: str
    role: str  # "applicant" | "reviewer"
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class UserResponse(BaseModel):
    """Public user representation (never exposes password)."""
    id: str
    email: str
    role: str
    name: str
    created_at: datetime


class UserCreate(BaseModel):
    email: str
    password: str
    role: str  # "applicant" | "reviewer"
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
