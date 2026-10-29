import re
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status, UploadFile, File, Form
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.database import get_db
from app.models.entities import ResumeVersion, Document, CandidatePII
from app.schemas.dtos import (
    ImprovementResponse, SaveVersionRequest, ResumeVersionResponse,
    RecalculateScoreRequest, RecalculateScoreResponse
)
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
        personal_overrides=personal_overrides,
        approved_changes=request.approved_changes
    )

class SaveDraftRequest(BaseModel):
    change_summary: Optional[str] = "Draft saved from Resume Improvement"
    revised_content: Optional[str] = None
    candidate_name: Optional[str] = None
    candidate_role: Optional[str] = None
    candidate_phone: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_location: Optional[str] = None
    candidate_links: Optional[str] = None
    approved_changes: Optional[List[dict]] = None

@router.post("/api/resumes/{doc_id}/save-draft")
def save_draft(
    doc_id: str,
    request: SaveDraftRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Saves current improvement modifications as a new Draft Document in Resume Library & IKM.
    Generates valid DOCX, assigns new DOC-XXXX ID, maintains candidate association,
    and preserves original resume file completely intact.
    """
    personal_overrides = {
        "name": request.candidate_name,
        "role": request.candidate_role,
        "phone": request.candidate_phone,
        "email": request.candidate_email,
        "location": request.candidate_location,
        "links": request.candidate_links
    }
    return resume_improvement_service.save_draft_to_library(
        source_doc_id=doc_id,
        db=db,
        actor=current_user,
        file_bytes=None,
        change_summary=request.change_summary,
        revised_content=request.revised_content,
        personal_overrides=personal_overrides,
        approved_changes=request.approved_changes
    )

@router.post("/api/resumes/{doc_id}/save-editor-docx")
async def save_editor_docx(
    doc_id: str,
    file: UploadFile = File(...),
    change_summary: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Receives an edited DOCX file directly from WordCraft editor,
    persists it as an updated revision in DMS, updates version metadata,
    and recalculates alignment scoring.
    """
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="No file content received.")
    return resume_improvement_service.save_editor_docx(
        doc_id=doc_id,
        file_bytes=file_bytes,
        db=db,
        actor=current_user,
        change_summary=change_summary
    )

@router.post("/api/resumes/{doc_id}/save-to-library")
async def save_to_library(
    doc_id: str,
    file: Optional[UploadFile] = File(None),
    change_summary: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Persists the edited resume as a new record in Resume Library and IKM,
    assigning a unique document ID and maintaining revision relationship to original.
    """
    file_bytes = await file.read() if file else None
    return resume_improvement_service.save_draft_to_library(
        source_doc_id=doc_id,
        db=db,
        actor=current_user,
        file_bytes=file_bytes,
        change_summary=change_summary
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

    # 1. Primary: Download directly from IKM
    from app.integrations.ikm_adapter import ikm_adapter
    ver_bytes = None
    if hasattr(ikm_adapter, "_download_cache") and version_id in ikm_adapter._download_cache:
        ver_bytes = ikm_adapter._download_cache[version_id]
    if not ver_bytes and version_rec.dms_ref:
        if version_rec.dms_ref.startswith("ikm://"):
            ver_bytes = ikm_adapter.download_document(version_rec.dms_ref[6:])
        else:
            ver_bytes = ikm_adapter.download_document(version_rec.dms_ref)
    if not ver_bytes:
        doc = db.query(Document).filter(Document.doc_id == version_rec.doc_id).first()
        found = ikm_adapter.find_document_by_name(f"{doc.original_filename.rsplit('.', 1)[0]}_{version_id}.docx" if doc else f"{version_id}.docx")
        if found and found.get("document_id"):
            ver_bytes = ikm_adapter.download_document(found["document_id"])
    if not ver_bytes and version_rec.revised_content:
        from app.services.word_resume_service import word_resume_service
        doc_tmp = db.query(Document).filter(Document.doc_id == version_rec.doc_id).first()
        cand_name_tmp = doc_tmp.original_filename.rsplit(".", 1)[0] if doc_tmp else "Candidate"
        ver_bytes = word_resume_service.generate_improved_docx_bytes(
            candidate_name=cand_name_tmp,
            target_role="Senior Professional",
            profile={},
            revised_content=version_rec.revised_content
        )

    doc = db.query(Document).filter(Document.doc_id == version_rec.doc_id).first()
    base_name = doc.original_filename.rsplit(".", 1)[0] if doc else version_id

    if ver_bytes:
        # Restore any contact details masked by remote IKM redaction engine for authorized download
        if version_rec.doc_id:
            pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == version_rec.doc_id).first()
            if pii_rec:
                from app.security.encryption import pii_crypto
                decrypted = pii_crypto.decrypt_pii_dict({
                    "name_encrypted": pii_rec.name_encrypted,
                    "email_encrypted": pii_rec.email_encrypted,
                    "phone_encrypted": pii_rec.phone_encrypted,
                    "address_encrypted": pii_rec.address_encrypted
                })
                real_phone = decrypted.get("phone")
                real_email = decrypted.get("email")
                if real_phone or real_email:
                    if ver_bytes.startswith(b"PK"):
                        try:
                            import docx
                            import io
                            import re
                            d = docx.Document(io.BytesIO(ver_bytes))
                            modified = False
                            for p in d.paragraphs:
                                orig_txt = p.text
                                new_txt = orig_txt
                                if real_phone and "+XXX-XXX-XXXX" in new_txt:
                                    new_txt = new_txt.replace("+XXX-XXX-XXXX", real_phone)
                                if real_email and "***@" in new_txt:
                                    new_txt = re.sub(r'[\w\.-]+\*{3}@[\w\.-]+', real_email, new_txt)
                                if new_txt != orig_txt:
                                    for r in p.runs:
                                        if real_phone and "+XXX-XXX-XXXX" in r.text:
                                            r.text = r.text.replace("+XXX-XXX-XXXX", real_phone)
                                        if real_email and "***@" in r.text:
                                            r.text = re.sub(r'[\w\.-]+\*{3}@[\w\.-]+', real_email, r.text)
                                    if "+XXX-XXX-XXXX" in p.text or "***@" in p.text:
                                        p.text = new_txt
                                    modified = True
                            if modified:
                                out_io = io.BytesIO()
                                d.save(out_io)
                                ver_bytes = out_io.getvalue()
                        except Exception:
                            pass
                    else:
                        if real_phone and b"+XXX-XXX-XXXX" in ver_bytes:
                            ver_bytes = ver_bytes.replace(b"+XXX-XXX-XXXX", real_phone.encode("utf-8"))
                        if real_email:
                            import re
                            ver_bytes = re.sub(rb'[\w\.-]+\*{3}@[\w\.-]+', real_email.encode("utf-8"), ver_bytes)

        from fastapi.responses import Response
        import urllib.parse
        is_docx = (ver_bytes.startswith(b"PK") or "docx" in str(version_rec.dms_ref).lower())
        fn = f"{base_name}_Improved_Resume.docx" if is_docx else f"{base_name}_Improved.txt"
        encoded_fn = urllib.parse.quote(fn)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if is_docx else "text/plain"
        return Response(
            content=ver_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{fn}"; filename*=UTF-8\'\'{encoded_fn}'}
        )

    # 2. Local file fallback if exists
    file_path = dms_adapter.get_file_path(version_rec.dms_ref)
    if file_path and file_path.exists():
        if file_path.suffix.lower() == ".docx":
            return FileResponse(
                path=file_path,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=f"{base_name}_Improved_Resume.docx",
                headers={"Content-Disposition": "inline"}
            )
        return FileResponse(
            path=file_path,
            media_type="text/plain",
            filename=f"{base_name}_Improved.txt",
            headers={"Content-Disposition": "inline"}
        )

    if version_rec.revised_content:
        return PlainTextResponse(
            content=version_rec.revised_content,
            headers={"Content-Disposition": f"attachment; filename={version_id}.txt"}
        )

    raise HTTPException(status_code=404, detail="Version file not found in storage.")

@router.get("/api/versions/{version_id}/preview")
def get_version_preview(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Returns an in-application paginated preview of a revised resume version,
    preventing unwanted downloads.
    """
    from app.services.resume_preview_service import resume_preview_service
    return resume_preview_service.get_version_preview(version_id, db)

class GenerateWordRequest(BaseModel):
    change_summary: str = "AI Enhanced Word Resume with verified project metrics."
    revised_content: Optional[str] = ""
    target_role: Optional[str] = "Senior Professional"
    candidate_name: Optional[str] = None
    candidate_role: Optional[str] = None
    candidate_phone: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_location: Optional[str] = None
    candidate_links: Optional[str] = None
    personal_details: Optional[dict] = None
    approved_changes: Optional[List[dict]] = None

@router.post("/api/resumes/{doc_id}/recalculate-score", response_model=RecalculateScoreResponse)
def recalculate_candidate_score(
    doc_id: str,
    request: RecalculateScoreRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Honest score recalculation based on recruiter-approved resume changes.
    Evaluates newly verified evidence and updates alignment score.
    """
    accepted_dicts = [c.dict() if hasattr(c, "dict") else dict(c) for c in request.accepted_changes]
    return resume_improvement_service.recalculate_score(
        doc_id=doc_id,
        job_id=request.job_id,
        job_text=request.job_text,
        accepted_changes=accepted_dicts,
        db=db
    )

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

    # If content provided is minimal or generic placeholder (and not an original docx), synthesize with Groq engine
    is_orig_docx = bool((doc.original_filename and doc.original_filename.lower().endswith(".docx")) or (doc.dms_ref and "docx" in doc.dms_ref.lower()))
    if not is_orig_docx and (len(content_to_use) < 100 or content_to_use.startswith("CANDIDATE PROFILE -")):
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
        personal_overrides=personal_overrides,
        approved_changes=request.approved_changes
    )
    clean_name = re.sub(r'[^\w\s-]', '', cand_name or '').strip()
    clean_name = re.sub(r'[-\s]+', '_', clean_name)
    clean_role = re.sub(r'[^\w\s-]', '', target_role or cand_role or '').strip()
    clean_role = re.sub(r'[-\s]+', '_', clean_role)

    if clean_name and clean_role:
        filename = f"{clean_name}_{clean_role}.docx"
    elif clean_name:
        filename = f"{clean_name}_Improved_Resume.docx"
    elif clean_role:
        filename = f"Resume_{clean_role}.docx"
    else:
        filename = f"{doc_id}_Improved_Resume.docx"

    # Also save that version to our library with filename having fullname_jobrole
    library_doc_id = None
    try:
        docx_bytes = ver.get("file_bytes")
        if not docx_bytes and ver.get("dms_ref"):
            from app.integrations.ikm_adapter import ikm_adapter
            ref = ver["dms_ref"]
            if ref.startswith("ikm://"):
                ref = ref[6:]
            docx_bytes = ikm_adapter.download_document(ref)
        if not docx_bytes:
            docx_file_path = dms_adapter.get_file_path(ver.get("dms_ref"))
            if docx_file_path and docx_file_path.exists():
                with open(docx_file_path, "rb") as f_in:
                    docx_bytes = f_in.read()

        if docx_bytes:
            lib_res = resume_improvement_service.save_draft_to_library(
                source_doc_id=doc_id,
                db=db,
                actor=current_user,
                file_bytes=docx_bytes,
                change_summary=f"Improved Resume for {target_role}",
                custom_filename=filename
            )
            library_doc_id = lib_res.get("doc_id")
    except Exception as e_lib:
        import logging
        logging.getLogger(__name__).warning(f"Could not persist version to library: {e_lib}")

    return {
        "success": True,
        "doc_id": doc_id,
        "version_id": ver["version_id"],
        "filename": filename,
        "download_url": f"/api/versions/{ver['version_id']}/file",
        "message": f"Successfully generated Word resume '{filename}'",
        "actual_score": ver.get("actual_score"),
        "score_breakdown": ver.get("score_breakdown"),
        "score_delta": ver.get("score_delta"),
        "score_explanation": ver.get("score_explanation"),
        "library_doc_id": library_doc_id
    }

@router.post("/api/resumes/{doc_id}/open-in-word")
def open_in_local_word(
    doc_id: str,
    request: Optional[GenerateWordRequest] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Generates the improved .docx resume file and opens it directly in local Microsoft Word on Windows.
    """
    req = request or GenerateWordRequest()
    res = generate_word_resume(doc_id, req, db, current_user)
    version_id = res["version_id"]
    version_rec = db.query(ResumeVersion).filter(ResumeVersion.version_id == version_id).first()
    file_path = dms_adapter.get_file_path(version_rec.dms_ref) if version_rec else None

    opened_locally = False
    open_error = None
    try:
        import os
        import subprocess
        import platform
        if platform.system() == "Windows" and file_path and file_path.exists():
            resolved = str(file_path.resolve())
            try:
                os.startfile(resolved)
                opened_locally = True
            except Exception as e_start:
                open_error = str(e_start)
                # Fallback to direct WINWORD.EXE execution
                word_candidates = [
                    r"C:\Program Files\Microsoft Office\Root\Office16\WINWORD.EXE",
                    r"C:\Program Files (x86)\Microsoft Office\Root\Office16\WINWORD.EXE",
                    r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
                    r"C:\Program Files\Microsoft Office\Office15\WINWORD.EXE",
                ]
                for wp in word_candidates:
                    if os.path.exists(wp):
                        subprocess.Popen([wp, resolved])
                        opened_locally = True
                        open_error = None
                        break
    except Exception as e:
        open_error = str(e)

    return {
        "success": True,
        "opened_locally": opened_locally,
        "version_id": version_id,
        "filename": res["filename"],
        "download_url": res["download_url"],
        "actual_score": res.get("actual_score"),
        "score_breakdown": res.get("score_breakdown"),
        "score_delta": res.get("score_delta"),
        "score_explanation": res.get("score_explanation"),
        "message": "Opened resume in Microsoft Word." if opened_locally else (f"Could not launch local Word ({open_error}). Document ready to download." if open_error else "Document prepared. Download to edit in Microsoft Word.")
    }

@router.post("/api/resumes/{doc_id}/open-folder")
def open_candidate_folder(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Opens Windows File Explorer with the candidate's selected resume file highlighted.
    """
    # Prefer latest revised version file
    version_rec = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.doc_id == doc_id)
        .order_by(ResumeVersion.created_at.desc())
        .first()
    )
    file_path = None
    if version_rec and version_rec.dms_ref:
        file_path = dms_adapter.get_file_path(version_rec.dms_ref)
    if not file_path or not file_path.exists():
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if doc and doc.dms_ref:
            file_path = dms_adapter.get_file_path(doc.dms_ref)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Candidate resume file for '{doc_id}' not found on disk.")

    resolved = str(file_path.resolve())
    import subprocess
    import platform
    if platform.system() == "Windows":
        try:
            subprocess.Popen(f'explorer.exe /select,"{resolved}"')
            return {
                "success": True,
                "file_path": resolved,
                "folder": str(file_path.parent.resolve()),
                "message": f"Opened folder with file selected: {file_path.name}"
            }
        except Exception as e:
            return {"success": False, "message": f"Could not launch Windows Explorer: {e}"}
    return {"success": False, "message": "Opening explorer folder is supported on Windows."}


