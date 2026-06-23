"""
Application model — SQLAlchemy ORM + Pydantic schemas.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy import String, Float, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

VALID_STATUSES = ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "RETURNED_FOR_CHANGES"]

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT":                {"SUBMITTED"},
    "SUBMITTED":            {"UNDER_REVIEW", "RETURNED_FOR_CHANGES"},
    "UNDER_REVIEW":         {"APPROVED", "REJECTED"},
    "RETURNED_FOR_CHANGES": {"DRAFT"},
    "APPROVED":  set(),
    "REJECTED":  set(),
}


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    applicant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT")
    reviewer_comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    attachment_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ApplicationCreate(BaseModel):
    title: str
    category: str
    description: str = ""
    amount: float = 0.0


class ApplicationUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None


class ApplicationResponse(BaseModel):
    id: int
    title: str
    category: str
    description: str
    amount: float
    applicant_id: str
    status: str
    reviewer_comment: str
    created_at: datetime
    updated_at: datetime
    attachment_url: Optional[str] = None
    model_config = {"from_attributes": True}


class ApplicationListResponse(BaseModel):
    applications: List[ApplicationResponse]
    total: int


class TransitionRequest(BaseModel):
    action: str
    comment: str = ""


class ApplicationInDB(BaseModel):
    """Lightweight model used by tests — duck-typed with .status attribute."""
    id: str = "fake-id"
    title: str = ""
    category: str = ""
    description: str = ""
    amount: float = 0.0
    applicant_id: str = "test@test.com"
    status: str = "DRAFT"
    reviewer_comment: str = ""
    attachment_url: Optional[str] = None
