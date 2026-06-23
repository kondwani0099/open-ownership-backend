"""
User model — SQLAlchemy ORM + Pydantic schemas.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_notif_read: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    name: str
    created_at: datetime
    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str
    password: str
    role: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
