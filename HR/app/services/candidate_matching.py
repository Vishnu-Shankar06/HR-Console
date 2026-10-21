import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.entities import Document, CandidateProfile, JobDescription, MatchRun, MatchResult, AuditEvent
from app.integrations.llm_adapter import llm_adapter
from app.services.scoring_service import scoring_service
from app.security.rbac import CurrentUser

class CandidateMatchingService:
    """
    Candidate matching service.
    Validates manually typable numeric Top-N, computes grounded scores,
    and returns ranked candidates with verbatim evidence and gaps.
    """

    def run_matching(
        self,
        requested_count: int,
        db: Session,
        actor: CurrentUser,
        job_id: Optional[str] = None,
        job_description_text: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        doc_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        # 1. Validation of manually typed candidate count
        if not isinstance(requested_count, int) or requested_count <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Candidate shortlist count must be a valid positive integer greater than 0."
            )
        if requested_count > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shortlist count exceeds maximum threshold of 100."
            )

        # 2. Resolve Job Description
        job_record = None
        if job_id:
            job_record = db.query(JobDescription).filter(JobDescription.job_id == job_id).first()
            if not job_record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job description with ID '{job_id}' not found."
                )
            jd_reqs = job_record.requirements_json
            job_title = job_record.title
        elif job_description_text and job_description_text.strip():
            jd_reqs = llm_adapter.parse_job_description(job_description_text)
            job_title = jd_reqs.get("title", "Position")
            # Auto-save dynamic JD
            dyn_job_id = f"JOB-{uuid.uuid4().hex[:6].upper()}"
            job_record = JobDescription(
                job_id=dyn_job_id,
                title=job_title,
                source_ref="adhoc_typed",
                raw_text=job_description_text,
                requirements_json=jd_reqs,
                created_by=actor.user_id,
                created_at=datetime.now(timezone.utc)
            )
            db.add(job_record)
            db.commit()
            job_id = dyn_job_id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide either a valid job_id or non-empty job_description_text."
            )

        # 3. Retrieve ready candidate documents
        query = db.query(Document).filter(Document.upload_status == "ready")
        if doc_ids is not None:
            query = query.filter(Document.doc_id.in_(doc_ids))
        ready_docs = query.all()

        if not ready_docs:
            notice = (
                "No eligible candidate matches found among the uploaded resume files."
                if doc_ids is not None
                else "No processed resumes are currently registered in the system. Please upload candidate resumes first."
            )
            return {
                "run_id": f"RUN-{uuid.uuid4().hex[:8]}",
                "job_id": job_id,
                "job_title": job_title,
                "requested_count": requested_count,
                "returned_count": 0,
                "results": [],
                "notice": notice
            }

        # 4. Score and evaluate each candidate
        scored_candidates = []
        for doc in ready_docs:
            profile_record = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc.doc_id).first()
            if not profile_record or not profile_record.structured_profile_json:
                continue

            profile = profile_record.structured_profile_json
            
            # Transparent scoring engine
            score_data = scoring_service.calculate_score(jd_reqs, profile)
            # Evidence & gap reasoning
            explanation_data = llm_adapter.explain_candidate_match(jd_reqs, profile)

            scored_candidates.append({
                "doc_id": doc.doc_id,
                "candidate_label": f"Candidate {doc.doc_id}",
                "internal_match_score": score_data["total_score"],
                "score_breakdown": score_data["breakdown"],
                "matched_requirements": explanation_data["matched_requirements"],
                "gaps": explanation_data["gaps"],
                "explanation": explanation_data["explanation"],
                "review_required": True
            })

        # 5. Sort descending by internal match score
        scored_candidates.sort(key=lambda c: c["internal_match_score"], reverse=True)

        # Assign ranks
        for idx, cand in enumerate(scored_candidates):
            cand["rank"] = idx + 1

        # Apply top-N limit
        top_candidates = scored_candidates[:requested_count]
        returned_count = len(top_candidates)

        # 6. Notice if fewer candidates were available than requested
        notice = None
        if doc_ids is not None:
            if returned_count < requested_count:
                notice = (
                    f"Evaluated {len(ready_docs)} uploaded candidate resume(s). Found {returned_count} eligible match(es) "
                    f"(requested shortlist size: {requested_count})."
                )
        else:
            if returned_count < requested_count:
                notice = (
                    f"You requested {requested_count} candidates, but only {returned_count} eligible "
                    f"resumes are currently processed in the system. Showing all {returned_count} matches."
                )

        # 7. Persist MatchRun & MatchResults
        run_id = f"RUN-{uuid.uuid4().hex[:8]}"
        run_record = MatchRun(
            run_id=run_id,
            job_id=job_id,
            requested_count=requested_count,
            returned_count=returned_count,
            config_version="standard-v1",
            created_by=actor.user_id,
            created_at=datetime.now(timezone.utc),
            status="completed"
        )
        db.add(run_record)

        for cand in top_candidates:
            res_record = MatchResult(
                run_id=run_id,
                doc_id=cand["doc_id"],
                rank=cand["rank"],
                score=cand["internal_match_score"],
                score_breakdown_json=cand["score_breakdown"],
                evidence_json={
                    "matched": cand["matched_requirements"],
                    "gaps": cand["gaps"],
                    "explanation": cand["explanation"]
                },
                review_status="pending"
            )
            db.add(res_record)

        # Audit event
        db.add(AuditEvent(
            event_id=f"aud-{uuid.uuid4().hex[:8]}",
            actor_id=actor.user_id,
            action="candidate_match_run",
            target_doc_id=None,
            outcome="success",
            metadata_json={"job_id": job_id, "requested": requested_count, "returned": returned_count}
        ))

        db.commit()

        return {
            "run_id": run_id,
            "job_id": job_id,
            "job_title": job_title,
            "requested_count": requested_count,
            "returned_count": returned_count,
            "results": top_candidates,
            "notice": notice
        }

candidate_matching_service = CandidateMatchingService()
