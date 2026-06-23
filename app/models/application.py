"""
Application model — the core domain object.

Status workflow (state machine):
    DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED
                                       → REJECTED
                        → RETURNED_FOR_CHANGES → DRAFT
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

# ── Valid statuses ──────────────────────────────────────────────────────────────
VALID_STATUSES = [
    "DRAFT",
    "SUBMITTED",
    "UNDER_REVIEW",
    "APPROVED",
    "REJECTED",
    "RETURNED_FOR_CHANGES",
]

# ── Legal transitions (from → {to}) ─────────────────────────────────────────────
LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT":                {"SUBMITTED"},
    "SUBMITTED":            {"UNDER_REVIEW", "RETURNED_FOR_CHANGES"},
    "UNDER_REVIEW":         {"APPROVED", "REJECTED"},
    "RETURNED_FOR_CHANGES": {"DRAFT"},
    # Terminal states — no outgoing transitions
    "APPROVED":  set(),
    "REJECTED":  set(),
}


class ApplicationInDB(BaseModel):
    """Full application document as stored in MongoDB."""
    id: Optional[str] = Field(None, alias="_id")
    title: str
    category: str
    description: str = ""
    amount: float = 0.0
    applicant_id: str          # email of the applicant
    status: str = "DRAFT"
    reviewer_comment: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    attachment_url: Optional[str] = None

    class Config:
        populate_by_name = True


class ApplicationCreate(BaseModel):
    """Payload for creating a new application (always starts as DRAFT)."""
    title: str
    category: str
    description: str = ""
    amount: float = 0.0


class ApplicationUpdate(BaseModel):
    """Payload for editing a DRAFT application."""
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None


class ApplicationResponse(BaseModel):
    """Public application representation."""
    id: str
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


class ApplicationListResponse(BaseModel):
    applications: List[ApplicationResponse]
    total: int


class TransitionRequest(BaseModel):
    """Payload for a status transition (submit / review / return)."""
    action: str  # "submit" | "review" | "approve" | "reject" | "return"
    comment: str = ""
