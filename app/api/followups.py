from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.database import get_db
from app.schemas.dtos import FollowUpItem, RecordActionRequest, DevelopmentPlanResponse
from app.services.followup_service import followup_service
from app.security.rbac import get_current_user, CurrentUser

router = APIRouter(tags=["Follow-ups & Candidate Development"])

class DevelopmentPlanRequest(BaseModel):
    target_role: Optional[str] = None

@router.get("/api/follow-ups", response_model=List[FollowUpItem])
def list_followups(
    inactivity_days: Optional[int] = Query(None, description="Inactivity threshold days (default 7)"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Identifies old/inactive candidate records:
    - Resumes with no recorded action for N days
    - Candidates with overdue next-action dates
    - Returns suggested next recruiter actions
    """
    return followup_service.get_inactive_and_due_resumes(db, inactivity_days)

@router.get("/api/resumes/{doc_id}/actions")
def get_candidate_actions(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Returns complete chronological history of recruiter actions and remarks for a candidate.
    """
    from app.models.entities import RecruitmentAction
    actions = (
        db.query(RecruitmentAction)
        .filter(RecruitmentAction.doc_id == doc_id)
        .order_by(RecruitmentAction.action_at.desc())
        .all()
    )
    return [
        {
            "action_id": a.action_id,
            "doc_id": a.doc_id,
            "action_type": a.action_type,
            "status": a.status,
            "owner_id": a.owner_id,
            "notes": a.notes,
            "action_at": a.action_at.isoformat() if a.action_at else None,
            "next_action_at": a.next_action_at.isoformat() if a.next_action_at else None
        }
        for a in actions
    ]

class AddRemarkRequest(BaseModel):
    notes: str
    status: Optional[str] = None

@router.post("/api/resumes/{doc_id}/remarks")
def add_candidate_remark(
    doc_id: str,
    request: AddRemarkRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Stores an explicit recruiter remark/note for a candidate with optional status update.
    """
    # Fetch current latest status if status not explicitly provided
    from app.models.entities import RecruitmentAction
    latest_act = (
        db.query(RecruitmentAction)
        .filter(RecruitmentAction.doc_id == doc_id)
        .order_by(RecruitmentAction.action_at.desc())
        .first()
    )
    status_to_use = request.status or (latest_act.status if latest_act else "reviewed")
    
    res = followup_service.record_recruitment_action(
        doc_id=doc_id,
        action_type="remark_added",
        db=db,
        actor=current_user,
        status_val=status_to_use,
        notes=request.notes.strip(),
        owner_id=current_user.user_id
    )
    res["success"] = True
    return res

@router.post("/api/resumes/{doc_id}/actions")
def record_action(
    doc_id: str,
    request: RecordActionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Records a recruiter action:
    - Action types: reviewed, contacted, shortlisted, hired, rejected, snooze, follow_up_scheduled
    - Updates workflow status and resets next action date
    """
    return followup_service.record_recruitment_action(
        doc_id=doc_id,
        action_type=request.action_type,
        db=db,
        actor=current_user,
        status_val=request.status,
        notes=request.notes,
        owner_id=request.owner_id,
        next_action_at=request.next_action_at
    )


@router.post("/api/resumes/{doc_id}/development-plan", response_model=DevelopmentPlanResponse)
def generate_development_plan(
    doc_id: str,
    request: Optional[DevelopmentPlanRequest] = None,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Generates tailored candidate development plan:
    - Practical projects to demonstrate missing requirements
    - Verified learning resources
    - Optional certification advice
    - Recruiter outreach message draft
    """
    target = request.target_role if request else None
    return followup_service.generate_candidate_development_plan(
        doc_id=doc_id,
        db=db,
        actor=current_user,
        target_role=target
    )

@router.post("/api/resumes/{doc_id}/open")
def record_resume_opened(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Records when a recruiter opens or inspects a candidate resume,
    updating the last_opened_at timestamp.
    """
    ts = followup_service.record_resume_opened(doc_id, db)
    return {"doc_id": doc_id, "last_opened_at": ts.isoformat()}

@router.get("/api/notifications")
def get_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retrieves system notifications and candidate dormancy alerts.
    """
    # Trigger refresh/sync
    followup_service.get_inactive_and_due_resumes(db)
    return followup_service.get_notifications(db, unread_only=unread_only)

@router.post("/api/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    success = followup_service.mark_notification_read(notification_id, db)
    return {"success": success}

@router.post("/api/resumes/{doc_id}/send-escalation-email")
def send_candidate_escalation_email(
    doc_id: str,
    recipient: Optional[str] = Query("damayanthi.u@riscrm.com"),
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    AI Agent endpoint: Sends an automated escalation email to damayanthi.u@riscrm.com
    with the candidate resume attached and dormancy rationale.
    """
    from app.services.email_agent import email_agent
    return email_agent.send_dormancy_escalation_email(
        doc_id=doc_id,
        db=db,
        recipient_email=recipient,
        reason=reason
    )

