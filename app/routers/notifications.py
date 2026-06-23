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
from app.models.audit_log import AuditLog
from app.models.user import User, UserResponse
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
    Uses the user's stored last_notif_read timestamp if no since param.
    """
    # Resolve the cutoff: explicit since > stored last_notif_read
    cutoff = None
    if since:
        try:
            cutoff = datetime.fromisoformat(since)
        except ValueError:
            pass
    else:
        db_user = await db.get(User, user.id)
        if db_user and db_user.last_notif_read:
            cutoff = db_user.last_notif_read

    if user.role == "applicant":
        app_ids_q = select(Application.id).where(Application.applicant_id == user.email)
        app_ids = [r[0] for r in (await db.execute(app_ids_q)).all()]
        if not app_ids:
            return {"notifications": [], "unread": 0}
        q = select(AuditLog).where(
            and_(AuditLog.application_id.in_(app_ids), AuditLog.performer_role == "reviewer")
        )
    else:
        q = select(AuditLog).where(
            or_(AuditLog.new_status == "SUBMITTED", AuditLog.performed_by == user.email)
        )

    if cutoff:
        q = q.where(AuditLog.timestamp > cutoff)

    q = q.order_by(AuditLog.timestamp.desc()).limit(limit)
    results = (await db.execute(q)).scalars().all()

    notifications = []
    unread_count = 0
    for log in results:
        app = await db.get(Application, log.application_id)
        app_title = app.title if app else "(deleted)"
        notifications.append({
            "id": log.id, "application_id": log.application_id,
            "application_title": app_title, "performed_by": log.performed_by,
            "performer_role": log.performer_role, "old_status": log.old_status,
            "new_status": log.new_status, "comment": log.comment,
            "timestamp": log.timestamp.isoformat(),
        })
        # Count as unread if newer than stored last_notif_read
        if cutoff and log.timestamp > cutoff:
            unread_count += 1
        elif not cutoff:
            unread_count += 1

    return {"notifications": notifications, "unread": unread_count}


@router.put("/read")
async def mark_notifications_read(
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read by updating the user's last_notif_read timestamp."""
    db_user = await db.get(User, user.id)
    if db_user:
        db_user.last_notif_read = datetime.now(timezone.utc)
        await db.commit()
    return {"status": "ok"}
