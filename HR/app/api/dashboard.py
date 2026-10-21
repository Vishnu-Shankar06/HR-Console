from collections import Counter
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.entities import Document, CandidateProfile, JobDescription, RecruitmentAction, AuditEvent
from app.schemas.dtos import DashboardSummaryResponse
from app.services.followup_service import followup_service
from app.security.rbac import get_current_user, CurrentUser

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    total_docs = db.query(Document).filter(Document.upload_status == "ready").count()
    active_jobs = db.query(JobDescription).filter(JobDescription.source_ref != "adhoc_typed").count()


    follow_ups = followup_service.get_inactive_and_due_resumes(db)
    follow_ups_due = sum(1 for f in follow_ups if f["is_overdue"] or f["status"] == "pending_review" or f["is_stale"])
    overdue_count = sum(1 for f in follow_ups if f["is_overdue"])
    awaiting_review = sum(1 for f in follow_ups if f["status"] == "pending_review")

    # Skill distribution
    profiles = db.query(CandidateProfile).all()
    skill_counter = Counter()
    for p in profiles:
        if p.structured_profile_json:
            for s in p.structured_profile_json.get("skills", []):
                skill_counter[s] += 1
    top_skills = dict(skill_counter.most_common(8))

    # Recent activity
    recent_actions = (
        db.query(RecruitmentAction)
        .order_by(RecruitmentAction.action_at.desc())
        .limit(10)
        .all()
    )
    activity_items = [
        {
            "action_id": a.action_id,
            "doc_id": a.doc_id,
            "action_type": a.action_type,
            "status": a.status,
            "owner_id": a.owner_id,
            "timestamp": a.action_at.isoformat() if a.action_at else None,
            "notes": a.notes
        }
        for a in recent_actions
    ]

    return DashboardSummaryResponse(
        total_resumes=total_docs,
        awaiting_review=awaiting_review,
        follow_ups_due=follow_ups_due,
        overdue_count=overdue_count,
        active_jobs=active_jobs,
        top_skills_distribution=top_skills,
        recent_activity=activity_items
    )
