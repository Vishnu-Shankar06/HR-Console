import re
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
    total_docs = db.query(Document).count()
    active_jobs = db.query(JobDescription).filter(JobDescription.source_ref != "adhoc_typed").count()


    follow_ups = followup_service.get_inactive_and_due_resumes(db)
    follow_ups_due = sum(1 for f in follow_ups if f["is_overdue"] or f["status"] == "pending_review" or f["is_stale"])
    overdue_count = sum(1 for f in follow_ups if f["is_overdue"])
    awaiting_review = sum(1 for f in follow_ups if f["status"] == "pending_review")

    # Follow-ups status distribution for pie chart
    status_counter = Counter()
    for f in follow_ups:
        if f.get("is_overdue"):
            status_counter["Overdue"] += 1
        elif f.get("status") == "pending_review":
            status_counter["Pending Review"] += 1
        elif f.get("status") == "shortlisted":
            status_counter["Shortlisted"] += 1
        elif f.get("status") == "contacted":
            status_counter["Contacted"] += 1
        elif f.get("status") == "snooze":
            status_counter["Snoozed"] += 1
        elif f.get("status") == "rejected":
            status_counter["Rejected"] += 1
        elif f.get("status") == "hired":
            status_counter["Hired"] += 1
        elif f.get("is_stale"):
            status_counter["Stale Inactive"] += 1
        else:
            label = (f.get("status") or "Active").replace("_", " ").title()
            status_counter[label] += 1

    # Skill distribution - select only JSON column to avoid loading massive raw text summaries
    profile_jsons = db.query(CandidateProfile.structured_profile_json).all()
    skill_counter = Counter()
    for (p_json,) in profile_jsons:
        if p_json and isinstance(p_json, dict):
            for s in p_json.get("skills", []):
                skill_counter[s] += 1
    top_skills = dict(skill_counter.most_common(8))

    # Recent activity with candidate names and details
    recent_actions = (
        db.query(RecruitmentAction)
        .order_by(RecruitmentAction.action_at.desc())
        .limit(10)
        .all()
    )

    doc_ids = [a.doc_id for a in recent_actions if a.doc_id]
    doc_map = {}
    if doc_ids:
        docs = db.query(Document).filter(Document.doc_id.in_(doc_ids)).all()
        for d in docs:
            name = d.original_filename.rsplit(".", 1)[0] if d.original_filename else d.doc_id
            clean_name = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc)$', '', name, flags=re.IGNORECASE)
            clean_name = re.sub(r'[\-_]+', ' ', clean_name).strip()
            doc_map[d.doc_id] = clean_name.title() if clean_name else d.doc_id
        try:
            from app.models.entities import CandidatePII
            from app.security.encryption import pii_crypto
            piis = db.query(CandidatePII).filter(CandidatePII.doc_id.in_(doc_ids)).all()
            for p in piis:
                if p.name_encrypted:
                    dec = pii_crypto.decrypt_pii_dict({"name_encrypted": p.name_encrypted})
                    if dec.get("name") and dec["name"].upper() not in ["SUMMARY", "OBJECTIVE", "PROFILE", "RESUME"]:
                        doc_map[p.doc_id] = dec["name"]
        except Exception:
            pass

    activity_items = [
        {
            "action_id": a.action_id,
            "doc_id": a.doc_id,
            "candidate_name": doc_map.get(a.doc_id, a.doc_id or "System"),
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
        recent_activity=activity_items,
        followup_status_distribution=dict(status_counter)
    )
