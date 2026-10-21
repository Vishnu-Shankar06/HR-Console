from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.entities import MatchRun, MatchResult, JobDescription
from app.schemas.dtos import MatchRequest, MatchRunResponse, MatchResultItem
from app.services.candidate_matching import candidate_matching_service
from app.security.rbac import get_current_user, CurrentUser

router = APIRouter(prefix="/api/matches", tags=["Candidate Matching"])

@router.post("", response_model=MatchRunResponse)
def match_candidates(
    request: MatchRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Executes candidate matching:
    - Validates manually typed candidate count N (must be positive integer, > 0, <= 100)
    - Compares verified candidate evidence against JD requirements
    - Calculates transparent 5-dimension score (Mandatory 35%, Technical 25%, Experience 20%, Education 10%, Evidence 10%)
    - Explains results with verbatim citations and gaps
    - Never fabricates candidates if fewer than N are found
    """
    return candidate_matching_service.run_matching(
        requested_count=request.requested_count,
        db=db,
        actor=current_user,
        job_id=request.job_id,
        job_description_text=request.job_description_text,
        filters=request.filters,
        doc_ids=request.doc_ids
    )

@router.get("/{run_id}", response_model=MatchRunResponse)
def get_match_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    run_record = db.query(MatchRun).filter(MatchRun.run_id == run_id).first()
    if not run_record:
        raise HTTPException(status_code=404, detail=f"Match run '{run_id}' not found.")

    job = db.query(JobDescription).filter(JobDescription.job_id == run_record.job_id).first()
    results = (
        db.query(MatchResult)
        .filter(MatchResult.run_id == run_id)
        .order_by(MatchResult.rank.asc())
        .all()
    )

    items = []
    for r in results:
        ev = r.evidence_json or {}

        cand_name = None
        pii_data = None
        pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == r.doc_id).first()
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
                "doc_id": r.doc_id,
                "name": cand_name,
                "email": decrypted.get("email"),
                "phone": decrypted.get("phone"),
                "address": decrypted.get("address")
            }
        if not cand_name:
            doc = db.query(Document).filter(Document.doc_id == r.doc_id).first()
            if doc:
                import re
                clean = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc)$', '', doc.original_filename, flags=re.IGNORECASE)
                clean = re.sub(r'[\-_]+', ' ', clean).strip()
                cand_name = clean.title() if clean else f"Candidate {r.doc_id}"

        # Current status
        actions = (
            db.query(RecruitmentAction)
            .filter(RecruitmentAction.doc_id == r.doc_id)
            .order_by(RecruitmentAction.action_at.desc())
            .all()
        )
        cand_status = r.review_status or "pending_review"
        if actions:
            has_hired = any(a.status == "hired" or a.action_type == "hired" for a in actions)
            if has_hired:
                cand_status = "hired"
            else:
                for a in actions:
                    if a.action_type in ["hired", "rejected", "shortlisted", "contacted", "snooze", "reviewed", "remark_added"]:
                        cand_status = a.status
                        break

        items.append(MatchResultItem(
            rank=r.rank,
            doc_id=r.doc_id,
            candidate_label=cand_name or f"Candidate {r.doc_id}",
            candidate_name=cand_name,
            full_name=cand_name,
            current_status=cand_status,
            pii=pii_data,
            internal_match_score=int(r.score),
            score_breakdown=r.score_breakdown_json,
            matched_requirements=ev.get("matched", []),
            gaps=ev.get("gaps", []),
            explanation=ev.get("explanation", ""),
            review_required=True
        ))

    notice = None
    if run_record.returned_count < run_record.requested_count:
        notice = f"Found {run_record.returned_count} eligible candidates (requested {run_record.requested_count})."

    return MatchRunResponse(
        run_id=run_record.run_id,
        job_id=run_record.job_id,
        job_title=job.title if job else "Position",
        requested_count=run_record.requested_count,
        returned_count=run_record.returned_count,
        results=items,
        notice=notice
    )
