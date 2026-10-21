import uuid
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.entities import JobDescription, AuditEvent, MatchRun, MatchResult
from app.schemas.dtos import JobCreateRequest, JobResponse
from app.integrations.llm_adapter import llm_adapter
from app.security.rbac import get_current_user, CurrentUser

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

@router.post("", response_model=JobResponse)
def create_job(
    request: JobCreateRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Creates a new Job Description record from typed or pasted text.
    Decomposes into mandatory, technical, experience, and qualification criteria.
    """
    parsed_reqs = llm_adapter.parse_job_description(request.job_text)
    job_id = f"JOB-{uuid.uuid4().hex[:6].upper()}"

    job_record = JobDescription(
        job_id=job_id,
        title=request.title or parsed_reqs.get("title", "Position"),
        source_ref="saved_requisition",
        raw_text=request.job_text,
        requirements_json=parsed_reqs,
        created_by=current_user.user_id,
        created_at=datetime.now(timezone.utc)
    )
    db.add(job_record)

    db.add(AuditEvent(
        event_id=f"aud-{uuid.uuid4().hex[:8]}",
        actor_id=current_user.user_id,
        action="create_job_description",
        target_doc_id=None,
        outcome="success",
        metadata_json={"job_id": job_id, "title": job_record.title}
    ))

    db.commit()

    return JobResponse(
        job_id=job_id,
        title=job_record.title,
        created_at=job_record.created_at,
        created_by=job_record.created_by,
        requirements=job_record.requirements_json,
        preview_snippet=job_record.raw_text[:200]
    )

@router.get("", response_model=List[JobResponse])
def list_jobs(
    include_adhoc: bool = False,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Lists active job openings. Excludes ephemeral ad-hoc search queries by default
    so the saved jobs dropdown remains clean.
    """
    q = db.query(JobDescription)
    if not include_adhoc:
        q = q.filter(JobDescription.source_ref != "adhoc_typed")
    jobs = q.order_by(JobDescription.created_at.desc()).all()
    return [
        JobResponse(
            job_id=j.job_id,
            title=j.title,
            created_at=j.created_at,
            created_by=j.created_by,
            requirements=j.requirements_json,
            preview_snippet=j.raw_text[:200]
        )
        for j in jobs
    ]

@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    j = db.query(JobDescription).filter(JobDescription.job_id == job_id).first()
    if not j:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return JobResponse(
        job_id=j.job_id,
        title=j.title,
        created_at=j.created_at,
        created_by=j.created_by,
        requirements=j.requirements_json,
        preview_snippet=j.raw_text[:200]
    )

@router.delete("/{job_id}")
def delete_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Deletes an active job opening and any associated match runs.
    """
    j = db.query(JobDescription).filter(JobDescription.job_id == job_id).first()
    if not j:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    # Delete related match runs and match results
    match_runs = db.query(MatchRun).filter(MatchRun.job_id == job_id).all()
    for mr in match_runs:
        db.query(MatchResult).filter(MatchResult.run_id == mr.run_id).delete()
        db.delete(mr)

    db.delete(j)
    db.commit()
    return {"success": True, "message": f"Job opening '{job_id}' deleted successfully."}
