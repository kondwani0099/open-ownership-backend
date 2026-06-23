"""
Audit log model — SQLAlchemy ORM + Pydantic schemas.
"""

from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(Integer, ForeignKey("applications.id"), nullable=False)
    performed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    performer_role: Mapped[str] = mapped_column(String(50), nullable=False)
    old_status: Mapped[str] = mapped_column(String(50), nullable=False)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLogResponse(BaseModel):
    id: int
    application_id: int
    performed_by: str
    performer_role: str
    old_status: str
    new_status: str
    comment: str
    timestamp: datetime
    model_config = {"from_attributes": True}
