"""
Applications router — CRUD + transitions for the submission & approval workflow.
PostgreSQL / SQLAlchemy async edition.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.application import (
    Application,
    ApplicationCreate,
    ApplicationUpdate,
    ApplicationResponse,
    ApplicationListResponse,
    TransitionRequest,
)
from app.models.audit_log import AuditLog, AuditLogResponse
from app.models.user import UserResponse
from app.routers.auth import get_current_user, require_role
from app.services.state_machine import (
    validate_transition_raw,
    resolve_action,
    IllegalTransitionError,
    MissingCommentError,
)

router = APIRouter(prefix="/applications", tags=["Applications"])


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_app_or_404(app_id: str, db: AsyncSession) -> Application:
    try:
        app_id_int = int(app_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid application ID")
    app = await db.get(Application, app_id_int)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


async def _record_audit(
    db: AsyncSession,
    application_id: int,
    performer_email: str,
    performer_role: str,
    old_status: str,
    new_status: str,
    comment: str = "",
):
    entry = AuditLog(
        application_id=application_id,
        performed_by=performer_email,
        performer_role=performer_role,
        old_status=old_status,
        new_status=new_status,
        comment=comment,
    )
    db.add(entry)
    await db.commit()


# ── Applicant Endpoints ────────────────────────────────────────────────────────

@router.post("/", response_model=ApplicationResponse, status_code=201)
async def create_application(
    body: ApplicationCreate,
    user: UserResponse = Depends(require_role("applicant")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new application (always starts as DRAFT)."""
    app = Application(
        title=body.title,
        category=body.category,
        description=body.description,
        amount=body.amount,
        applicant_id=user.email,
        status="DRAFT",
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    await _record_audit(db, app.id, user.email, user.role, "", "DRAFT", "Application created")
    return ApplicationResponse.model_validate(app)


@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: str,
    body: ApplicationUpdate,
    user: UserResponse = Depends(require_role("applicant")),
    db: AsyncSession = Depends(get_db),
):
    """Edit a DRAFT application. Only the owner may do this."""
    app = await _get_app_or_404(application_id, db)

    if app.applicant_id != user.email:
        raise HTTPException(status_code=403, detail="You can only edit your own applications")
    if app.status != "DRAFT":
        raise HTTPException(status_code=403, detail="Only DRAFT applications can be edited")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    for key, value in updates.items():
        setattr(app, key, value)

    await db.commit()
    await db.refresh(app)
    return ApplicationResponse.model_validate(app)


@router.get("/mine", response_model=ApplicationListResponse)
async def list_my_applications(
    user: UserResponse = Depends(require_role("applicant")),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List the authenticated applicant's own applications."""
    q = select(Application).where(Application.applicant_id == user.email)
    if status_filter:
        q = q.where(Application.status == status_filter)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(Application.updated_at.desc()).offset(offset).limit(limit)
    apps = (await db.execute(q)).scalars().all()

    return ApplicationListResponse(
        applications=[ApplicationResponse.model_validate(a) for a in apps],
        total=total,
    )


# ── Reviewer Endpoints ─────────────────────────────────────────────────────────

@router.get("/queue", response_model=ApplicationListResponse)
async def list_review_queue(
    user: UserResponse = Depends(require_role("reviewer")),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None, alias="search"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Reviewer queue: all applications, optionally filtered by status."""
    q = select(Application)

    if status_filter:
        q = q.where(Application.status == status_filter)

    if search:
        like = f"%{search}%"
        q = q.where(or_(
            Application.title.ilike(like),
            Application.description.ilike(like),
            Application.applicant_id.ilike(like),
        ))

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(Application.updated_at.desc()).offset(offset).limit(limit)
    apps = (await db.execute(q)).scalars().all()

    return ApplicationListResponse(
        applications=[ApplicationResponse.model_validate(a) for a in apps],
        total=total,
    )


# ── Shared Detail Endpoint ─────────────────────────────────────────────────────

@router.get("/{application_id}", response_model=dict)
async def get_application_detail(
    application_id: str,
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an application by ID with its full audit trail."""
    app = await _get_app_or_404(application_id, db)

    if user.role == "applicant" and app.applicant_id != user.email:
        raise HTTPException(status_code=403, detail="You can only view your own applications")

    audit_q = select(AuditLog).where(AuditLog.application_id == app.id).order_by(AuditLog.timestamp)
    audit_logs = (await db.execute(audit_q)).scalars().all()

    return {
        "application": ApplicationResponse.model_validate(app).model_dump(),
        "audit_logs": [AuditLogResponse.model_validate(a).model_dump() for a in audit_logs],
    }


# ── Transition Endpoint ────────────────────────────────────────────────────────

@router.post("/{application_id}/transition", response_model=ApplicationResponse)
async def transition_application(
    application_id: str,
    body: TransitionRequest,
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a status transition on an application."""
    app = await _get_app_or_404(application_id, db)

    try:
        target_status = resolve_action(body.action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Role-based authorization
    if body.action == "submit":
        if user.role != "applicant":
            raise HTTPException(status_code=403, detail="Only applicants can submit applications")
        if app.applicant_id != user.email:
            raise HTTPException(status_code=403, detail="You can only submit your own applications")
    elif body.action in ("review", "approve", "reject", "return"):
        if user.role != "reviewer":
            raise HTTPException(status_code=403, detail="Only reviewers can perform this action")
        if app.applicant_id == user.email:
            raise HTTPException(status_code=403, detail="Reviewers cannot act on their own applications")

    # Validate transition
    try:
        validate_transition_raw(app.status, target_status, body.comment)
    except IllegalTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except MissingCommentError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Execute
    old_status = app.status
    app.status = target_status
    if body.comment:
        app.reviewer_comment = body.comment

    await db.commit()
    await db.refresh(app)

    await _record_audit(db, app.id, user.email, user.role, old_status, target_status, body.comment)
    return ApplicationResponse.model_validate(app)
