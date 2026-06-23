"""
Audit log model — records every status transition with who, when, and comment.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AuditLogInDB(BaseModel):
    """Audit log document stored in MongoDB."""
    id: Optional[str] = Field(None, alias="_id")
    application_id: str
    performed_by: str       # email of the user
    performer_role: str     # "applicant" | "reviewer"
    old_status: str
    new_status: str
    comment: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class AuditLogResponse(BaseModel):
    """Public audit log representation."""
    id: str
    application_id: str
    performed_by: str
    performer_role: str
    old_status: str
    new_status: str
    comment: str
    timestamp: datetime
