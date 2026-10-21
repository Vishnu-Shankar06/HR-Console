import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.config import settings
from app.models.entities import Document, CandidateProfile, RecruitmentAction, AuditEvent, JobDescription, Notification, CandidatePII
from app.integrations.llm_adapter import llm_adapter
from app.security.rbac import CurrentUser

class FollowupService:
    """
    Workflow follow-up and candidate development service:
    - Configurable inactivity threshold detection (e.g. 7 days without action)
    - Overdue next-action date surfacing
    - Recruiter action logging (reviewed, contacted, shortlisted, rejected, snooze)
    - Grounded candidate development plan generation
    - Outreach message drafting
    """

    def get_inactive_and_due_resumes(
        self,
        db: Session,
        inactivity_days: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        threshold_days = inactivity_days or settings.DEFAULT_INACTIVITY_THRESHOLD_DAYS
        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(days=threshold_days)

        documents = db.query(Document).filter(Document.upload_status == "ready").all()
        follow_up_list = []

        for doc in documents:
            # Fetch latest recruitment action
            latest_action = (
                db.query(RecruitmentAction)
                .filter(RecruitmentAction.doc_id == doc.doc_id)
                .order_by(RecruitmentAction.action_at.desc())
                .first()
            )

            last_action_time = latest_action.action_at if latest_action else doc.uploaded_at
            if last_action_time.tzinfo is None:
                last_action_time = last_action_time.replace(tzinfo=timezone.utc)

            last_opened_time = getattr(doc, "last_opened_at", None) or last_action_time
            if last_opened_time.tzinfo is None:
                last_opened_time = last_opened_time.replace(tzinfo=timezone.utc)

            days_inactive = (now - last_action_time).days
            next_action_time = latest_action.next_action_at if latest_action else None
            if next_action_time and next_action_time.tzinfo is None:
                next_action_time = next_action_time.replace(tzinfo=timezone.utc)

            status_val = latest_action.status if latest_action else "pending_review"
            is_overdue = (next_action_time is not None and next_action_time < now and status_val != "hired")
            is_stale = (days_inactive >= threshold_days and status_val != "hired")

            # Check if notification exists or needs creation for dormant candidate
            notif = db.query(Notification).filter(Notification.doc_id == doc.doc_id).first()
            if (days_inactive >= threshold_days or is_overdue) and not notif:
                severity = "danger" if (days_inactive >= 90 or is_overdue) else "warning"
                title = f"3-Month Inactivity: Candidate {doc.doc_id}" if days_inactive >= 90 else f"Inactivity Notice: Candidate {doc.doc_id}"
                msg = f"Candidate {doc.doc_id} has not had any recruiter action recorded for {days_inactive} days."
                if is_overdue:
                    title = f"Overdue Follow-Up: Candidate {doc.doc_id}"
                    msg = f"Scheduled follow-up date for candidate {doc.doc_id} has passed without an update."
                
                notif = Notification(
                    id=f"notif-{uuid.uuid4().hex[:8]}",
                    doc_id=doc.doc_id,
                    title=title,
                    message=msg,
                    severity=severity,
                    days_inactive=days_inactive,
                    created_at=now
                )
                db.add(notif)
                try:
                    db.commit()
                except Exception:
                    db.rollback()

            # Suggested action formulation
            if is_overdue and status_val != "hired":
                suggested_act = "Follow-up deadline reached: Contact candidate or update status"
            elif status_val == "hired":
                suggested_act = "Candidate Hired: Onboarding and integration process underway"
            elif days_inactive >= 90:
                suggested_act = "Dormant (3+ months): Send follow-up check-in email or review candidate status"
            elif status_val == "pending_review":
                suggested_act = "New candidate: Review resume against open roles and screen qualifications"
            elif status_val == "shortlisted":
                suggested_act = "Schedule technical interview or follow up with hiring manager"
            elif status_val == "contacted":
                suggested_act = "Candidate contacted: Awaiting interview confirmation or feedback"
            elif days_inactive >= 14:
                suggested_act = "Review candidate qualifications against open requisition criteria"
            else:
                suggested_act = "Active candidate: Profile screened and aligned with pipeline"

            # Candidate name and contact PII
            cand_name = None
            pii_data = None
            pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == doc.doc_id).first()
            if pii_rec:
                from app.security.encryption import pii_crypto
                decrypted = pii_crypto.decrypt_pii_dict({
                    "name_encrypted": pii_rec.name_encrypted,
                    "email_encrypted": pii_rec.email_encrypted,
                    "phone_encrypted": pii_rec.phone_encrypted,
                    "address_encrypted": pii_rec.address_encrypted
                })
                cand_name = decrypted.get("name")
                pii_data = {
                    "doc_id": doc.doc_id,
                    "name": cand_name,
                    "email": decrypted.get("email"),
                    "phone": decrypted.get("phone"),
                    "address": decrypted.get("address")
                }
            if not cand_name:
                import re
                clean = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc)$', '', doc.original_filename, flags=re.IGNORECASE)
                clean = re.sub(r'[\-_]+', ' ', clean).strip()
                cand_name = clean.title() if clean else f"Candidate {doc.doc_id}"

            follow_up_list.append({
                "doc_id": doc.doc_id,
                "candidate_label": cand_name or f"Candidate {doc.doc_id}",
                "full_name": cand_name,
                "pii": pii_data,
                "status": status_val,
                "assigned_to": latest_action.owner_id if latest_action else doc.uploaded_by,
                "last_action_at": last_action_time,
                "last_action_type": latest_action.action_type if latest_action else "uploaded",
                "last_opened_at": last_opened_time,
                "days_inactive": max(0, days_inactive),
                "next_action_at": next_action_time,
                "is_overdue": is_overdue,
                "is_stale": is_stale,
                "notes": latest_action.notes if latest_action else None,
                "suggested_action": suggested_act,
                "email_sent": notif.email_sent if notif else False,
                "email_sent_to": notif.email_sent_to if notif else None,
                "email_sent_at": notif.email_sent_at if notif else None
            })

        # Sort: Overdue first, then 90+ days inactive, then new uploads, then most recently active
        follow_up_list.sort(key=lambda x: (
            not x["is_overdue"],
            not (x["days_inactive"] >= 90),
            x["status"] != "pending_review",
            -x["days_inactive"]
        ))
        return follow_up_list

    def record_resume_opened(self, doc_id: str, db: Session) -> datetime:
        """Records when a recruiter opens/views a candidate document."""
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        now = datetime.now(timezone.utc)
        if doc:
            doc.last_opened_at = now
            db.commit()
        return now

    def get_notifications(self, db: Session, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Retrieves system notifications and inactivity alerts."""
        q = db.query(Notification)
        if unread_only:
            q = q.filter(Notification.is_read == False)
        notifs = q.order_by(Notification.created_at.desc()).all()
        return [
            {
                "id": n.id,
                "doc_id": n.doc_id,
                "title": n.title,
                "message": n.message,
                "severity": n.severity,
                "days_inactive": n.days_inactive,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "is_read": n.is_read,
                "email_sent": n.email_sent,
                "email_sent_to": n.email_sent_to,
                "email_sent_at": n.email_sent_at.isoformat() if n.email_sent_at else None,
                "email_attachment_filename": n.email_attachment_filename
            }
            for n in notifs
        ]

    def mark_notification_read(self, notification_id: str, db: Session) -> bool:
        """Marks a notification as read."""
        n = db.query(Notification).filter(Notification.id == notification_id).first()
        if n:
            n.is_read = True
            db.commit()
            return True
        return False

    def record_recruitment_action(
        self,
        doc_id: str,
        action_type: str,
        db: Session,
        actor: CurrentUser,
        status_val: Optional[str] = None,
        notes: Optional[str] = None,
        owner_id: Optional[str] = None,
        next_action_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

        # Determine new status
        resolved_status = status_val or "reviewed"
        if action_type == "hired":
            resolved_status = "hired"
        elif action_type == "contacted":
            resolved_status = "contacted"
        elif action_type == "shortlisted":
            resolved_status = "shortlisted"
        elif action_type == "rejected":
            resolved_status = "rejected"
        elif action_type == "snooze":
            resolved_status = "in_progress"
            if not next_action_at:
                next_action_at = datetime.now(timezone.utc) + timedelta(days=7)

        action_id = f"act-{uuid.uuid4().hex[:8]}"
        action_record = RecruitmentAction(
            action_id=action_id,
            doc_id=doc_id,
            action_type=action_type,
            status=resolved_status,
            owner_id=owner_id or actor.user_id,
            notes=notes or f"Action '{action_type}' recorded by {actor.name}",
            action_at=datetime.now(timezone.utc),
            next_action_at=next_action_at
        )
        db.add(action_record)

        # Audit event
        db.add(AuditEvent(
            event_id=f"aud-{uuid.uuid4().hex[:8]}",
            actor_id=actor.user_id,
            action="record_recruitment_action",
            target_doc_id=doc_id,
            outcome="success",
            metadata_json={"action_type": action_type, "status": resolved_status}
        ))

        db.commit()

        return {
            "action_id": action_id,
            "doc_id": doc_id,
            "action_type": action_type,
            "status": resolved_status,
            "owner_id": action_record.owner_id,
            "action_at": action_record.action_at,
            "next_action_at": action_record.next_action_at,
            "notes": action_record.notes
        }

    def generate_candidate_development_plan(
        self,
        doc_id: str,
        db: Session,
        actor: CurrentUser,
        target_role: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates actionable candidate development plan:
        - Identifies gaps from latest matching or target role
        - Suggests practical projects, courses, certifications
        - Prepares recruiter-to-candidate outreach draft
        """
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

        profile_record = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
        if not profile_record:
            raise HTTPException(status_code=400, detail="Profile not processed.")

        profile = profile_record.structured_profile_json
        candidate_skills = {s.lower() for s in profile.get("skills", [])}
        
        # Determine likely missing areas for typical modern backend / cloud role
        target = target_role or "Python Backend & Cloud Engineer"
        all_key_skills = ["Docker", "Kubernetes", "PostgreSQL", "PyTest", "CI/CD", "Redis"]
        missing_skills = [s for s in all_key_skills if s.lower() not in candidate_skills]
        if not missing_skills:
            missing_skills = ["Microservices Architecture", "Performance Benchmarking"]

        plan = llm_adapter.generate_candidate_development_plan(missing_skills, target)

        # Audit event
        db.add(AuditEvent(
            event_id=f"aud-{uuid.uuid4().hex[:8]}",
            actor_id=actor.user_id,
            action="generate_candidate_development_plan",
            target_doc_id=doc_id,
            outcome="success",
            metadata_json={"target_role": target, "gaps": missing_skills}
        ))
        db.commit()

        return {
            "doc_id": doc_id,
            "target_role": target,
            "skill_gaps": missing_skills,
            "practical_projects": plan["practical_projects"],
            "learning_recommendations": plan["learning_recommendations"],
            "certifications": plan["certifications"],
            "recruiter_message_draft": plan["recruiter_message_draft"]
        }

followup_service = FollowupService()
