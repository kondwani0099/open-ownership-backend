"""
Notifications router — polls audit logs for relevant status changes.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.application import Application
from app.models.audit_log import AuditLog, AuditLogResponse
from app.models.user import UserResponse
from app.routers.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/")
async def get_notifications(
    user: UserResponse = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    since: Optional[str] = Query(None, description="ISO timestamp — only return newer"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return notifications for the current user.

    Applicant: sees audit logs for their own applications (approved/rejected/returned/comments).
    Reviewer: sees new submissions + audit logs they created.
    """
    if user.role == "applicant":
        # Get all application IDs belonging to this applicant
        app_ids_q = select(Application.id).where(Application.applicant_id == user.email)
        app_ids = [r[0] for r in (await db.execute(app_ids_q)).all()]

        if not app_ids:
            return {"notifications": [], "unread": 0}

        q = select(AuditLog).where(
            and_(
                AuditLog.application_id.in_(app_ids),
                AuditLog.performer_role == "reviewer",  # only reviewer actions
            )
        )
    else:
        # Reviewer: see submissions + their own audit actions
        q = select(AuditLog).where(
            or_(
                AuditLog.new_status == "SUBMITTED",
                AuditLog.performed_by == user.email,
            )
        )

    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            q = q.where(AuditLog.timestamp > since_dt)
        except ValueError:
            pass

    q = q.order_by(AuditLog.timestamp.desc()).limit(limit)
    results = (await db.execute(q)).scalars().all()

    notifications = []
    for log in results:
        # Fetch app title for context
        app = await db.get(Application, log.application_id)
        app_title = app.title if app else "(deleted)"

        notifications.append({
            "id": log.id,
            "application_id": log.application_id,
            "application_title": app_title,
            "performed_by": log.performed_by,
            "performer_role": log.performer_role,
            "old_status": log.old_status,
            "new_status": log.new_status,
            "comment": log.comment,
            "timestamp": log.timestamp.isoformat(),
        })

    # Count unread (all returned are "unread" — simplistic)
    return {
        "notifications": notifications,
        "unread": len(notifications),
    }
