from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.database import get_db
from app.models.entities import ResumeVersion, Document, CandidatePII
from app.schemas.dtos import ImprovementResponse, SaveVersionRequest, ResumeVersionResponse
from app.services.resume_improvement import resume_improvement_service
from app.integrations.dms_adapter import dms_adapter
from app.security.rbac import get_current_user, CurrentUser

router = APIRouter(tags=["Resume Improvement"])

class AnalyzeImprovementRequest(BaseModel):
    job_id: Optional[str] = None
    job_text: Optional[str] = None
    candidate_name: Optional[str] = None
    candidate_role: Optional[str] = None
    candidate_phone: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_location: Optional[str] = None
    candidate_links: Optional[str] = None
    personal_details: Optional[dict] = None

@router.post("/api/resumes/{doc_id}/improvements", response_model=ImprovementResponse)
def analyze_resume_gap(
    doc_id: str,
    body: AnalyzeImprovementRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Compares candidate resume with JD requirements:
    - Calculates transparent internal alignment score (never a 90% ATS guarantee)
    - Preserves candidate authentic personal contact details
    - Separates matched, partial, missing requirements, and formatting checks
    - Provides concrete rewrites with requires_user_confirmation flags
    """
    pd = body.personal_details or {}
    personal_overrides = {
        "name": body.candidate_name or pd.get("candidate_name") or pd.get("name"),
        "role": body.candidate_role or pd.get("candidate_role") or pd.get("role"),
        "phone": body.candidate_phone or pd.get("candidate_phone") or pd.get("phone"),
        "email": body.candidate_email or pd.get("candidate_email") or pd.get("email"),
        "location": body.candidate_location or pd.get("candidate_location") or pd.get("location"),
        "links": body.candidate_links or pd.get("candidate_links") or pd.get("links")
    }
    return resume_improvement_service.analyze_resume_for_job(
        doc_id=doc_id,
        db=db,
        actor=current_user,
        job_id=body.job_id,
        job_text=body.job_text,
        personal_overrides=personal_overrides
    )

@router.post("/api/resumes/{doc_id}/versions", response_model=ResumeVersionResponse)
def save_revised_version(
    doc_id: str,
    request: SaveVersionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Saves approved revised resume draft as a new version in DMS.
    Preserves original resume file completely intact.
    """
    personal_overrides = {
        "name": request.candidate_name,
        "role": request.candidate_role,
        "phone": request.candidate_phone,
        "email": request.candidate_email,
        "location": request.candidate_location,
        "links": request.candidate_links
    }
    return resume_improvement_service.save_revised_version(
        doc_id=doc_id,
        change_summary=request.change_summary,
        revised_content=request.revised_content,
        db=db,
        actor=current_user,
        approved=request.approved,
        personal_overrides=personal_overrides
    )

@router.get("/api/resumes/{doc_id}/versions", response_model=List[ResumeVersionResponse])
def get_version_history(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retrieves complete version history for a candidate resume record.
    """
    return resume_improvement_service.list_versions(doc_id, db)

@router.get("/api/versions/{version_id}/file")
def download_revised_file(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Streams the versioned revised resume file.
    """
    version_rec = db.query(ResumeVersion).filter(ResumeVersion.version_id == version_id).first()
    if not version_rec:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

    file_path = dms_adapter.get_file_path(version_rec.dms_ref)
    if not file_path or not file_path.exists():
        # Fallback stream content directly if file path is missing
        if version_rec.revised_content:
            return PlainTextResponse(
                content=version_rec.revised_content,
                headers={"Content-Disposition": f"attachment; filename={version_id}.txt"}
            )
        raise HTTPException(status_code=404, detail="Version file not found on disk.")

    doc = db.query(Document).filter(Document.doc_id == version_rec.doc_id).first()
    base_name = doc.original_filename.rsplit(".", 1)[0] if doc else version_id

    if file_path.suffix.lower() == ".docx":
        return FileResponse(
            path=file_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{base_name}_Improved_Resume.docx"
        )

    return FileResponse(
        path=file_path,
        media_type="text/plain",
        filename=f"{base_name}_Improved.txt"
    )

class GenerateWordRequest(BaseModel):
    change_summary: str = "AI Enhanced Word Resume with verified project metrics."
    revised_content: str
    target_role: Optional[str] = "Senior Professional"
    candidate_name: Optional[str] = None
    candidate_role: Optional[str] = None
    candidate_phone: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_location: Optional[str] = None
    candidate_links: Optional[str] = None
    personal_details: Optional[dict] = None

@router.post("/api/resumes/{doc_id}/generate-word")
def generate_word_resume(
    doc_id: str,
    request: GenerateWordRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    AI Agent endpoint: Generates an improved Microsoft Word (.docx) resume
    tailored to the target role, saves it as an immutable version in DMS,
    and returns direct download parameters.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    content_to_use = (request.revised_content or "").strip()
    target_role = request.target_role or "Senior Professional"

    pd = request.personal_details or {}
    cand_name = request.candidate_name or pd.get("candidate_name") or pd.get("name")
    cand_role = request.candidate_role or pd.get("candidate_role") or pd.get("role") or target_role
    cand_email = request.candidate_email or pd.get("candidate_email") or pd.get("email")
    cand_phone = request.candidate_phone or pd.get("candidate_phone") or pd.get("phone")
    cand_loc = request.candidate_location or pd.get("candidate_location") or pd.get("location")
    cand_links = request.candidate_links or pd.get("candidate_links") or pd.get("links")

    pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
    if pii_rec:
        from app.security.encryption import pii_crypto
        decrypted = pii_crypto.decrypt_pii_dict({
            "name_encrypted": pii_rec.name_encrypted,
            "email_encrypted": pii_rec.email_encrypted,
            "phone_encrypted": pii_rec.phone_encrypted,
            "address_encrypted": pii_rec.address_encrypted
        })
        if not cand_name and decrypted.get("name") and decrypted["name"].upper() not in ["SUMMARY", "OBJECTIVE", "PROFILE", "RESUME"]:
            cand_name = decrypted["name"]
        if not cand_email:
            cand_email = decrypted.get("email")
        if not cand_phone:
            cand_phone = decrypted.get("phone")
        if not cand_loc:
            cand_loc = decrypted.get("address")

    if not cand_name:
        import re
        fn = doc.original_filename
        clean = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc)$', '', fn, flags=re.IGNORECASE)
        clean = re.sub(r'[\-_]+', ' ', clean).strip()
        words = clean.split()
        clean_words = [w for w in words if w.lower() not in ['resume', 'cv', 'final', 'resumee', 'sfdc', 'developer', 'engineer', 'vault', 'qmsqdocs', 'qa', 'salesforce', 'se']]
        cand_name = ' '.join(clean_words).title() if clean_words else clean.title()

    personal_overrides = {
        "name": cand_name,
        "role": cand_role,
        "email": cand_email,
        "phone": cand_phone,
        "location": cand_loc,
        "links": cand_links
    }

    # If content provided is minimal or generic placeholder, synthesize with Grok engine
    if len(content_to_use) < 100 or content_to_use.startswith("CANDIDATE PROFILE -"):
        from app.models.entities import CandidateProfile
        from app.integrations.grok_adapter import grok_adapter
        prof_rec = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
        profile = prof_rec.structured_profile_json if prof_rec else {}
        raw_text = prof_rec.raw_text_summary if prof_rec else ""

        grok_res = grok_adapter.improve_resume(
            candidate_name=cand_name,
            raw_text=raw_text,
            profile=profile,
            jd_reqs={"title": target_role, "technical_skills": profile.get("skills", [])},
            target_role=target_role,
            gaps=[],
            matched=[],
            personal_details_override=personal_overrides
        )
        content_to_use = grok_res["improved_resume_text"]

    ver = resume_improvement_service.save_revised_version(
        doc_id=doc_id,
        change_summary=f"{request.change_summary} for {target_role}",
        revised_content=content_to_use,
        db=db,
        actor=current_user,
        approved=True,
        personal_overrides=personal_overrides
    )
    base_name = doc.original_filename.rsplit(".", 1)[0] if doc else doc_id
    filename = f"{base_name}_Improved_Resume.docx"

    return {
        "success": True,
        "version_id": ver["version_id"],
        "filename": filename,
        "download_url": f"/api/versions/{ver['version_id']}/file",
        "message": f"Successfully generated Word resume '{filename}'"
    }

