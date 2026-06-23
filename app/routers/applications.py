"""
Applications router — CRUD + transitions for the submission & approval workflow.

Authorization rules (enforced server-side):
  • Applicant: can create/edit/submit only their own DRAFT applications.
  • Reviewer: can review (approve/reject/return) only SUBMITTED/UNDER_REVIEW applications.
  • Nobody can approve their own application.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from bson import ObjectId

from app.database import (
    get_applications_collection,
    get_audit_logs_collection,
)
from app.models.application import (
    ApplicationInDB,
    ApplicationCreate,
    ApplicationUpdate,
    ApplicationResponse,
    ApplicationListResponse,
    TransitionRequest,
)
from app.models.audit_log import AuditLogInDB, AuditLogResponse
from app.models.user import UserResponse
from app.routers.auth import get_current_user, require_role
from app.services.state_machine import (
    validate_transition,
    validate_transition_raw,
    resolve_action,
    IllegalTransitionError,
    MissingCommentError,
)

router = APIRouter(prefix="/applications", tags=["Applications"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_response(doc: dict) -> ApplicationResponse:
    return ApplicationResponse(
        id=str(doc["_id"]),
        title=doc.get("title", ""),
        category=doc.get("category", ""),
        description=doc.get("description", ""),
        amount=doc.get("amount", 0.0),
        applicant_id=doc.get("applicant_id", ""),
        status=doc.get("status", "DRAFT"),
        reviewer_comment=doc.get("reviewer_comment", ""),
        created_at=doc.get("created_at", datetime.utcnow()),
        updated_at=doc.get("updated_at", datetime.utcnow()),
        attachment_url=doc.get("attachment_url"),
    )


def _audit_to_response(doc: dict) -> AuditLogResponse:
    return AuditLogResponse(
        id=str(doc["_id"]),
        application_id=doc.get("application_id", ""),
        performed_by=doc.get("performed_by", ""),
        performer_role=doc.get("performer_role", ""),
        old_status=doc.get("old_status", ""),
        new_status=doc.get("new_status", ""),
        comment=doc.get("comment", ""),
        timestamp=doc.get("timestamp", datetime.utcnow()),
    )


async def _get_app_or_404(app_id: str) -> dict:
    collection = get_applications_collection()
    try:
        doc = await collection.find_one({"_id": ObjectId(app_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid application ID format")
    if doc is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return doc


async def _record_audit(
    application_id: str,
    performer_email: str,
    performer_role: str,
    old_status: str,
    new_status: str,
    comment: str = "",
):
    collection = get_audit_logs_collection()
    entry = AuditLogInDB(
        application_id=application_id,
        performed_by=performer_email,
        performer_role=performer_role,
        old_status=old_status,
        new_status=new_status,
        comment=comment,
    )
    await collection.insert_one(entry.model_dump(by_alias=True, exclude={"id"}))


# ── Applicant Endpoints ────────────────────────────────────────────────────────

@router.post("/", response_model=ApplicationResponse, status_code=201)
async def create_application(
    body: ApplicationCreate,
    user: UserResponse = Depends(require_role("applicant")),
):
    """Create a new application (always starts as DRAFT)."""
    collection = get_applications_collection()
    now = datetime.now(timezone.utc)
    doc = {
        "title": body.title,
        "category": body.category,
        "description": body.description,
        "amount": body.amount,
        "applicant_id": user.email,
        "status": "DRAFT",
        "reviewer_comment": "",
        "created_at": now,
        "updated_at": now,
        "attachment_url": None,
    }
    result = await collection.insert_one(doc)
    doc["_id"] = result.inserted_id

    await _record_audit(
        application_id=str(result.inserted_id),
        performer_email=user.email,
        performer_role=user.role,
        old_status="",
        new_status="DRAFT",
        comment="Application created",
    )

    return _to_response(doc)


@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: str,
    body: ApplicationUpdate,
    user: UserResponse = Depends(require_role("applicant")),
):
    """Edit a DRAFT application. Only the owner may do this."""
    doc = await _get_app_or_404(application_id)

    if doc["applicant_id"] != user.email:
        raise HTTPException(status_code=403, detail="You can only edit your own applications")
    if doc["status"] != "DRAFT":
        raise HTTPException(status_code=403, detail="Only DRAFT applications can be edited")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc)

    collection = get_applications_collection()
    await collection.update_one(
        {"_id": ObjectId(application_id)},
        {"$set": updates},
    )

    doc.update(updates)
    return _to_response(doc)


@router.get("/mine", response_model=ApplicationListResponse)
async def list_my_applications(
    user: UserResponse = Depends(require_role("applicant")),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List the authenticated applicant's own applications."""
    collection = get_applications_collection()
    query: dict = {"applicant_id": user.email}
    if status_filter:
        query["status"] = status_filter

    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("updated_at", -1).skip(offset).limit(limit)
    apps = [_to_response(doc) async for doc in cursor]

    return ApplicationListResponse(applications=apps, total=total)


# ── Reviewer Endpoints ─────────────────────────────────────────────────────────

@router.get("/queue", response_model=ApplicationListResponse)
async def list_review_queue(
    user: UserResponse = Depends(require_role("reviewer")),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None, alias="search"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Reviewer queue: all applications, optionally filtered by status."""
    collection = get_applications_collection()
    query: dict = {}

    if status_filter:
        query["status"] = status_filter
    # When no filter, show ALL applications (includes APPROVED/REJECTED)

    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"applicant_id": {"$regex": search, "$options": "i"}},
        ]

    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("updated_at", -1).skip(offset).limit(limit)
    apps = [_to_response(doc) async for doc in cursor]

    return ApplicationListResponse(applications=apps, total=total)


# ── Shared Detail Endpoint ─────────────────────────────────────────────────────

@router.get("/{application_id}", response_model=dict)
async def get_application_detail(
    application_id: str,
    user: UserResponse = Depends(get_current_user),
):
    """Get an application by ID with its full audit trail."""
    doc = await _get_app_or_404(application_id)

    # Authorization: applicant sees only their own; reviewer sees all
    if user.role == "applicant" and doc["applicant_id"] != user.email:
        raise HTTPException(status_code=403, detail="You can only view your own applications")

    # Fetch audit log
    audit_collection = get_audit_logs_collection()
    audit_cursor = audit_collection.find({"application_id": application_id}).sort("timestamp", 1)
    audit_logs = [_audit_to_response(a) async for a in audit_cursor]

    return {
        "application": _to_response(doc).model_dump(),
        "audit_logs": [a.model_dump() for a in audit_logs],
    }


# ── Transition Endpoint ────────────────────────────────────────────────────────

@router.post("/{application_id}/transition", response_model=ApplicationResponse)
async def transition_application(
    application_id: str,
    body: TransitionRequest,
    user: UserResponse = Depends(get_current_user),
):
    """
    Execute a status transition on an application.

    Applicant actions: "submit" (DRAFT → SUBMITTED)
    Reviewer actions: "review", "approve", "reject", "return"

    Authorization is enforced:
      - Applicant can only submit their own DRAFT.
      - Reviewer can act on SUBMITTED / UNDER_REVIEW (not their own).
      - reject and return require a comment.
    """
    doc = await _get_app_or_404(application_id)
    current_status = doc["status"]
    doc_applicant_id = doc["applicant_id"]

    try:
        target_status = resolve_action(body.action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Role-based authorization ────────────────────────────────────────────
    if body.action == "submit":
        if user.role != "applicant":
            raise HTTPException(status_code=403, detail="Only applicants can submit applications")
        if doc_applicant_id != user.email:
            raise HTTPException(status_code=403, detail="You can only submit your own applications")

    elif body.action in ("review", "approve", "reject", "return"):
        if user.role != "reviewer":
            raise HTTPException(status_code=403, detail="Only reviewers can perform this action")
        if doc_applicant_id == user.email:
            raise HTTPException(status_code=403, detail="Reviewers cannot act on their own applications")

    # ── Validate transition ─────────────────────────────────────────────────
    try:
        validate_transition_raw(current_status, target_status, body.comment)
    except IllegalTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except MissingCommentError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Execute ─────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    update_fields = {
        "status": target_status,
        "updated_at": now,
    }
    if body.comment:
        update_fields["reviewer_comment"] = body.comment

    collection = get_applications_collection()
    await collection.update_one(
        {"_id": ObjectId(application_id)},
        {"$set": update_fields},
    )

    await _record_audit(
        application_id=application_id,
        performer_email=user.email,
        performer_role=user.role,
        old_status=current_status,
        new_status=target_status,
        comment=body.comment,
    )

    doc.update(update_fields)
    doc["status"] = target_status
    return _to_response(doc)
