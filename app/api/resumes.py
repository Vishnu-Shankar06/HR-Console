import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.database import get_db
from app.models.entities import Document, CandidateProfile, CandidatePII, ResumeVersion, RecruitmentAction, AuditEvent, MatchResult, Notification
from app.schemas.dtos import MultiUploadResponse, CandidateProfileDTO, DocumentDetailResponse, CandidatePIIDTO, BulkDeleteRequest, BulkDeleteResponse
from app.services.resume_ingestion import resume_ingestion_service
from app.integrations.dms_adapter import dms_adapter
from app.security.rbac import get_current_user, CurrentUser, require_role, UserRole
from app.security.encryption import pii_crypto

router = APIRouter(prefix="/api/resumes", tags=["Resumes"])

@router.post("", response_model=MultiUploadResponse)
async def upload_resumes(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Receives multiple resumes (PDF/DOCX/TXT).
    Assigns stable opaque doc_id (DOC-1001), stores original file in DMS,
    isolates and encrypts PII, extracts candidate profile, and indexes knowledge.
    One corrupt file does not fail the batch.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No resume files were provided."
        )
    return await resume_ingestion_service.ingest_batch(files, db, current_user)

@router.get("", response_model=List[DocumentDetailResponse])
def list_resumes(
    query: Optional[str] = Query(None, description="Search by doc_id, filename, or skill"),
    status_filter: Optional[str] = Query(None, description="Filter by upload status"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Search and list authorized candidate resume records with pagination.
    Omit protected PII by default to prevent unauthorized leakage.
    """
    # Ensure local database reflects live IKM repository status
    try:
        from app.services.ikm_sync_service import sync_ikm_with_database
        sync_ikm_with_database(db=db, force=False)
    except Exception:
        pass

    q = db.query(Document).options(
        joinedload(Document.profile),
        joinedload(Document.pii),
        selectinload(Document.actions),
        selectinload(Document.versions)
    )
    docs = q.order_by(Document.uploaded_at.desc()).offset(skip).limit(limit).all()

    results = []
    for doc in docs:
        ver_count = len(doc.versions) if doc.versions else 0
        actions = sorted(doc.actions, key=lambda a: a.action_at, reverse=True) if doc.actions else []
        cand_status = "pending_review"
        latest_act = actions[0] if actions else None
        if actions:
            has_hired = any(a.status == "hired" or a.action_type == "hired" for a in actions)
            if has_hired:
                cand_status = "hired"
            else:
                for a in actions:
                    if a.action_type in ["hired", "rejected", "shortlisted", "contacted", "snooze", "reviewed", "remark_added"]:
                        cand_status = a.status
                        break

        # Filter by status if provided (matches recruitment status like 'hired' or upload status)
        if status_filter and isinstance(status_filter, str):
            sf_low = status_filter.lower().strip()
            if cand_status.lower() != sf_low and doc.upload_status.lower() != sf_low:
                continue

        prof = doc.profile
        profile_dto = None
        if prof and prof.structured_profile_json:
            p_data = prof.structured_profile_json
            from app.services.experience_calculator import experience_calculator
            exp_list = p_data.get("experience", [])
            calc = p_data.get("experience_details")
            if not calc:
                if exp_list:
                    calc = experience_calculator.calculate_total_experience(exp_list)
                elif prof.raw_text_summary:
                    calc = experience_calculator.extract_experience_from_text(prof.raw_text_summary)
            exp_years = p_data.get("experience_years") or (calc.get("total_years") if calc else None)
            exp_display = p_data.get("experience_display") or (calc.get("display") if calc else None)
            if not exp_display and exp_years:
                exp_display = f"{exp_years} yrs"
            elif not exp_display:
                exp_display = "Not available"

            ikm_tpl = p_data.get("ikm_template") or {}
            cb = ikm_tpl.get("contact_block", {}) if isinstance(ikm_tpl, dict) else {}
            title_val = p_data.get("title") or cb.get("role") or p_data.get("domain") or "Software Engineer"
            links_val = cb.get("links") or p_data.get("links")
            loc_val = p_data.get("location") or cb.get("location")

            profile_dto = CandidateProfileDTO(
                doc_id=doc.doc_id,
                title=title_val,
                role=title_val,
                summary=p_data.get("summary") or ikm_tpl.get("summary"),
                skills=p_data.get("skills", []),
                qualifications=p_data.get("qualifications", []),
                experience=p_data.get("experience", []),
                projects=p_data.get("projects", []),
                certifications=p_data.get("certifications", []),
                profile_status=prof.profile_status,
                source_document_ref=doc.dms_ref,
                raw_text_summary=prof.raw_text_summary,
                experience_years=exp_years,
                experience_display=exp_display,
                experience_details=calc,
                location=loc_val,
                links=links_val,
                linkedin=cb.get("linkedin") or p_data.get("linkedin"),
                github=cb.get("github") or p_data.get("github"),
                portfolio=cb.get("portfolio") or p_data.get("portfolio")
            )

        # Decrypt PII to get candidate's full name and contact information
        cand_name = None
        pii_dto = None
        pii_rec = doc.pii
        if pii_rec:
            decrypted = pii_crypto.decrypt_pii_dict({
                "name_encrypted": pii_rec.name_encrypted,
                "email_encrypted": pii_rec.email_encrypted,
                "phone_encrypted": pii_rec.phone_encrypted,
                "address_encrypted": pii_rec.address_encrypted
            })
            cand_name = decrypted.get("name")
            p_data_ref = prof.structured_profile_json if (prof and prof.structured_profile_json) else {}
            ikm_ref_tpl = p_data_ref.get("ikm_template") or {}
            cb_ref = ikm_ref_tpl.get("contact_block", {}) if isinstance(ikm_ref_tpl, dict) else {}
            pii_dto = CandidatePIIDTO(
                doc_id=doc.doc_id,
                name=cand_name,
                title=profile_dto.title if profile_dto else (p_data_ref.get("title") or "Software Engineer"),
                role=profile_dto.role if profile_dto else (p_data_ref.get("role") or "Software Engineer"),
                email=decrypted.get("email"),
                phone=decrypted.get("phone"),
                address=decrypted.get("address") or cb_ref.get("location"),
                location=decrypted.get("address") or cb_ref.get("location"),
                links=cb_ref.get("links") or p_data_ref.get("links"),
                linkedin=cb_ref.get("linkedin") or p_data_ref.get("linkedin"),
                github=cb_ref.get("github") or p_data_ref.get("github"),
                portfolio=cb_ref.get("portfolio") or p_data_ref.get("portfolio"),
                filename=doc.original_filename,
                uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                experience_years=profile_dto.experience_years if profile_dto else None,
                experience_display=profile_dto.experience_display if profile_dto else "Not available",
                experience_details=profile_dto.experience_details if profile_dto else None,
                summary=profile_dto.summary if profile_dto else None,
                skills=profile_dto.skills if profile_dto else [],
                employment=profile_dto.experience if profile_dto else []
            )
        if not cand_name:
            import re
            clean = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc)$', '', doc.original_filename, flags=re.IGNORECASE)
            clean = re.sub(r'[\-_]+', ' ', clean).strip()
            cand_name = clean.title() if clean else f"Candidate {doc.doc_id}"

        # Filter by text search if provided
        if query:
            q_low = query.lower()
            match_doc = (
                q_low in doc.doc_id.lower() or
                (cand_name and q_low in cand_name.lower()) or
                q_low in doc.original_filename.lower() or
                (profile_dto and any(q_low in s.lower() for s in profile_dto.skills))
            )
            if not match_doc:
                continue

        results.append(DocumentDetailResponse(
            doc_id=doc.doc_id,
            original_filename=doc.original_filename,
            upload_status=doc.upload_status,
            uploaded_at=doc.uploaded_at,
            uploaded_by=doc.uploaded_by,
            profile=profile_dto,
            latest_status=cand_status,
            status=cand_status,
            next_action_at=latest_act.next_action_at if latest_act else None,
            versions_count=ver_count,
            full_name=cand_name,
            pii=pii_dto
        ))

    return results

@router.get("/{doc_id}", response_model=DocumentDetailResponse)
def get_resume_detail(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retrieves authorized candidate profile metadata and personal information for a document ID.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    prof = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc.doc_id).first()
    profile_dto = None
    if prof and prof.structured_profile_json:
        p_data = prof.structured_profile_json
        from app.services.experience_calculator import experience_calculator
        exp_list = p_data.get("experience", [])
        calc = p_data.get("experience_details")
        if not calc:
            if exp_list:
                calc = experience_calculator.calculate_total_experience(exp_list)
            elif prof.raw_text_summary:
                calc = experience_calculator.extract_experience_from_text(prof.raw_text_summary)
        exp_years = p_data.get("experience_years") or (calc.get("total_years") if calc else None)
        exp_display = p_data.get("experience_display") or (calc.get("display") if calc else None)
        if not exp_display and exp_years:
            exp_display = f"{exp_years} yrs"
        elif not exp_display:
            exp_display = "Not available"

        ikm_tpl = p_data.get("ikm_template") or {}
        cb = ikm_tpl.get("contact_block", {}) if isinstance(ikm_tpl, dict) else {}
        title_val = p_data.get("title") or cb.get("role") or p_data.get("domain") or "Software Engineer"
        links_val = cb.get("links") or p_data.get("links")
        loc_val = p_data.get("location") or cb.get("location")

        profile_dto = CandidateProfileDTO(
            doc_id=doc.doc_id,
            title=title_val,
            role=title_val,
            summary=p_data.get("summary") or ikm_tpl.get("summary"),
            skills=p_data.get("skills", []),
            qualifications=p_data.get("qualifications", []),
            experience=p_data.get("experience", []),
            projects=p_data.get("projects", []),
            certifications=p_data.get("certifications", []),
            profile_status=prof.profile_status,
            source_document_ref=doc.dms_ref,
            raw_text_summary=prof.raw_text_summary,
            experience_years=exp_years,
            experience_display=exp_display,
            experience_details=calc,
            location=loc_val,
            links=links_val,
            linkedin=cb.get("linkedin") or p_data.get("linkedin"),
            github=cb.get("github") or p_data.get("github"),
            portfolio=cb.get("portfolio") or p_data.get("portfolio")
        )

    cand_name = None
    pii_dto = None
    pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == doc.doc_id).first()
    if pii_rec:
        decrypted = pii_crypto.decrypt_pii_dict({
            "name_encrypted": pii_rec.name_encrypted,
            "email_encrypted": pii_rec.email_encrypted,
            "phone_encrypted": pii_rec.phone_encrypted,
            "address_encrypted": pii_rec.address_encrypted
        })
        cand_name = decrypted.get("name")
        p_data_ref = prof.structured_profile_json if (prof and prof.structured_profile_json) else {}
        ikm_ref_tpl = p_data_ref.get("ikm_template") or {}
        cb_ref = ikm_ref_tpl.get("contact_block", {}) if isinstance(ikm_ref_tpl, dict) else {}
        pii_dto = CandidatePIIDTO(
            doc_id=doc.doc_id,
            name=cand_name,
            title=profile_dto.title if profile_dto else (p_data_ref.get("title") or "Software Engineer"),
            role=profile_dto.role if profile_dto else (p_data_ref.get("role") or "Software Engineer"),
            email=decrypted.get("email"),
            phone=decrypted.get("phone"),
            address=decrypted.get("address") or cb_ref.get("location"),
            location=decrypted.get("address") or cb_ref.get("location"),
            links=cb_ref.get("links") or p_data_ref.get("links"),
            linkedin=cb_ref.get("linkedin") or p_data_ref.get("linkedin"),
            github=cb_ref.get("github") or p_data_ref.get("github"),
            portfolio=cb_ref.get("portfolio") or p_data_ref.get("portfolio"),
            filename=doc.original_filename,
            uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            experience_years=profile_dto.experience_years if profile_dto else None,
            experience_display=profile_dto.experience_display if profile_dto else "Not available",
            experience_details=profile_dto.experience_details if profile_dto else None,
            summary=profile_dto.summary if profile_dto else None,
            skills=profile_dto.skills if profile_dto else [],
            employment=profile_dto.experience if profile_dto else []
        )
    if not cand_name:
        import re
        clean = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc)$', '', doc.original_filename, flags=re.IGNORECASE)
        clean = re.sub(r'[\-_]+', ' ', clean).strip()
        cand_name = clean.title() if clean else f"Candidate {doc.doc_id}"

    ver_count = db.query(ResumeVersion).filter(ResumeVersion.doc_id == doc.doc_id).count()
    actions = (
        db.query(RecruitmentAction)
        .filter(RecruitmentAction.doc_id == doc.doc_id)
        .order_by(RecruitmentAction.action_at.desc())
        .all()
    )
    cand_status = "pending_review"
    latest_act = actions[0] if actions else None
    if actions:
        has_hired = any(a.status == "hired" or a.action_type == "hired" for a in actions)
        if has_hired:
            cand_status = "hired"
        else:
            for a in actions:
                if a.action_type in ["hired", "rejected", "shortlisted", "contacted", "snooze", "reviewed", "remark_added"]:
                    cand_status = a.status
                    break

    return DocumentDetailResponse(
        doc_id=doc.doc_id,
        original_filename=doc.original_filename,
        upload_status=doc.upload_status,
        uploaded_at=doc.uploaded_at,
        uploaded_by=doc.uploaded_by,
        profile=profile_dto,
        latest_status=cand_status,
        status=cand_status,
        next_action_at=latest_act.next_action_at if latest_act else None,
        versions_count=ver_count,
        full_name=cand_name,
        pii=pii_dto
    )

@router.get("/{doc_id}/pii", response_model=CandidatePIIDTO)
def get_resume_pii(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retrieves decrypted personal information and complete authorized candidate metadata.
    Restricted to authorized roles and logs an audit trail event.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    pii_record = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
    decrypted = {}
    if pii_record:
        decrypted = pii_crypto.decrypt_pii_dict({
            "name_encrypted": pii_record.name_encrypted,
            "email_encrypted": pii_record.email_encrypted,
            "phone_encrypted": pii_record.phone_encrypted,
            "address_encrypted": pii_record.address_encrypted
        })

    prof = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
    p_data = prof.structured_profile_json if (prof and prof.structured_profile_json) else {}
    from app.services.experience_calculator import experience_calculator
    exp_list = p_data.get("experience", [])
    calc = p_data.get("experience_details")
    if not calc:
        if exp_list:
            calc = experience_calculator.calculate_total_experience(exp_list)
        elif prof and prof.raw_text_summary:
            calc = experience_calculator.extract_experience_from_text(prof.raw_text_summary)

    exp_years = p_data.get("experience_years") or (calc.get("total_years") if calc else None)
    exp_display = p_data.get("experience_display") or (calc.get("display") if calc else None)
    if not exp_display and exp_years:
        exp_display = f"{exp_years} yrs"
    elif not exp_display:
        exp_display = "Not available"

    cand_name = decrypted.get("name")
    if not cand_name:
        import re
        clean = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc)$', '', doc.original_filename, flags=re.IGNORECASE)
        clean = re.sub(r'[\-_]+', ' ', clean).strip()
        cand_name = clean.title() if clean else f"Candidate {doc.doc_id}"

    ikm_tpl = p_data.get("ikm_template") or {}
    cb = ikm_tpl.get("contact_block", {}) if isinstance(ikm_tpl, dict) else {}
    title_val = p_data.get("title") or cb.get("role") or p_data.get("domain") or "Software Engineer"
    links_val = cb.get("links") or p_data.get("links")
    loc_val = decrypted.get("address") or cb.get("location") or p_data.get("location") or ""

    # Record sensitive access audit event
    db.add(AuditEvent(
        event_id=f"aud-{uuid.uuid4().hex[:8]}",
        actor_id=current_user.user_id,
        action="view_candidate_pii",
        target_doc_id=doc_id,
        outcome="authorized",
        metadata_json={"actor_role": current_user.role.value}
    ))
    db.commit()

    return CandidatePIIDTO(
        doc_id=doc_id,
        name=cand_name,
        title=title_val,
        role=title_val,
        email=decrypted.get("email"),
        phone=decrypted.get("phone"),
        address=loc_val,
        location=loc_val,
        links=links_val,
        linkedin=cb.get("linkedin") or p_data.get("linkedin"),
        github=cb.get("github") or p_data.get("github"),
        portfolio=cb.get("portfolio") or p_data.get("portfolio"),
        filename=doc.original_filename,
        uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        experience_years=exp_years,
        experience_display=exp_display,
        experience_details=calc,
        summary=p_data.get("summary") or ikm_tpl.get("summary"),
        skills=p_data.get("skills", []),
        employment=exp_list
    )

@router.get("/{doc_id}/file")
def get_original_file(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Authorized streaming of the original resume document stored in IKM or DMS.
    Ensures safe access control.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    # Audit log access
    db.add(AuditEvent(
        event_id=f"aud-{uuid.uuid4().hex[:8]}",
        actor_id=current_user.user_id,
        action="download_original_resume",
        target_doc_id=doc_id,
        outcome="success",
        metadata_json={"filename": doc.original_filename}
    ))
    db.commit()

    # 1. Primary Storage: Check IKM
    from app.integrations.ikm_adapter import ikm_adapter
    ikm_bytes = None
    if doc.ikm_ref:
        ikm_bytes = ikm_adapter.download_document(doc.ikm_ref)
    if not ikm_bytes and doc.dms_ref and doc.dms_ref.startswith("ikm://"):
        ikm_bytes = ikm_adapter.download_document(doc.dms_ref[6:])
    if not ikm_bytes:
        found = ikm_adapter.find_document_by_name(doc.original_filename)
        if found and found.get("document_id"):
            ikm_bytes = ikm_adapter.download_document(found["document_id"])

    if ikm_bytes:
        from fastapi.responses import Response
        import urllib.parse
        encoded_fn = urllib.parse.quote(doc.original_filename)
        return Response(
            content=ikm_bytes,
            media_type=doc.mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{doc.original_filename}"; filename*=UTF-8\'\'{encoded_fn}'}
        )

    # 2. Local disk fallback if exists
    file_path = dms_adapter.get_file_path(doc.dms_ref)
    if file_path and file_path.exists():
        return FileResponse(
            path=file_path,
            media_type=doc.mime_type,
            filename=doc.original_filename
        )

    raise HTTPException(status_code=404, detail="Original document file not found in IKM storage.")

@router.get("/{doc_id}/preview")
def get_resume_preview(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Returns an in-application paginated preview representation of the candidate resume,
    preventing unwanted downloads.
    """
    from app.services.resume_preview_service import resume_preview_service
    return resume_preview_service.get_document_preview(doc_id, db)

@router.get("/{doc_id}/stream")
def stream_resume_inline(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Streams the resume file with Content-Disposition: inline to prevent download prompts.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    # 1. Primary: Download directly from IKM
    from app.integrations.ikm_adapter import ikm_adapter
    ikm_bytes = None
    if doc.ikm_ref:
        ikm_bytes = ikm_adapter.download_document(doc.ikm_ref)
    if not ikm_bytes and doc.dms_ref and doc.dms_ref.startswith("ikm://"):
        ikm_bytes = ikm_adapter.download_document(doc.dms_ref[6:])
    if not ikm_bytes:
        found = ikm_adapter.find_document_by_name(doc.original_filename)
        if found and found.get("document_id"):
            ikm_bytes = ikm_adapter.download_document(found["document_id"])

    if ikm_bytes:
        from fastapi.responses import Response
        media_type = "application/pdf" if ikm_bytes.startswith(b"%PDF") else ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ikm_bytes.startswith(b"PK") else (doc.mime_type or "application/octet-stream"))
        return Response(content=ikm_bytes, media_type=media_type, headers={"Content-Disposition": "inline"})

    # 2. Local file fallback if exists
    file_path = dms_adapter.get_file_path(doc.dms_ref)
    if file_path and file_path.exists() and file_path.stat().st_size > 0:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            media_type = "application/pdf"
        elif suffix in [".docx", ".doc"]:
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            media_type = doc.mime_type or "application/octet-stream"

        return FileResponse(
            path=file_path,
            media_type=media_type,
            headers={"Content-Disposition": "inline"}
        )

    # 3. Candidate profile fallback for seeded/in-memory records
    from app.models.entities import CandidateProfile, CandidatePII
    prof_rec = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
    if prof_rec:
        raw_text = prof_rec.raw_text_summary or ""
        cand_name = doc.original_filename.rsplit(".", 1)[0] if doc.original_filename else "Candidate"
        pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
        if pii_rec and pii_rec.name_encrypted:
            from app.security.encryption import pii_crypto
            d = pii_crypto.decrypt_pii_dict({"name_encrypted": pii_rec.name_encrypted})
            if d.get("name"):
                cand_name = d["name"]
        skills_str = ", ".join(prof_rec.structured_profile_json.get("skills", [])) if (prof_rec.structured_profile_json and prof_rec.structured_profile_json.get("skills")) else ""
        content_text = f"{cand_name}\n\n{raw_text}\n\nSkills: {skills_str}".strip()
        from fastapi.responses import Response
        return Response(content=content_text.encode("utf-8"), media_type=doc.mime_type or "text/plain", headers={"Content-Disposition": "inline"})

    raise HTTPException(status_code=404, detail="Original document file not found in storage.")

@router.delete("/{doc_id}")
def delete_resume(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Deletes a candidate resume record and its associated data (PII, profile, revisions, actions).
    Cleans up files from IKM and DMS.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    # Delete related match results
    db.query(MatchResult).filter(MatchResult.doc_id == doc_id).delete()
    # Delete recruitment actions
    db.query(RecruitmentAction).filter(RecruitmentAction.doc_id == doc_id).delete()

    # Delete versions from IKM and DB
    from app.integrations.ikm_adapter import ikm_adapter
    versions = db.query(ResumeVersion).filter(ResumeVersion.doc_id == doc_id).all()
    for v in versions:
        if v.dms_ref and v.dms_ref.startswith("ikm://"):
            ikm_adapter.delete_document(v.dms_ref[6:], filename=f"{doc_id}_{v.version_id}")
        elif v.dms_ref:
            ikm_adapter.delete_document(v.dms_ref, filename=f"{doc_id}_{v.version_id}")
    db.query(ResumeVersion).filter(ResumeVersion.doc_id == doc_id).delete()

    # Delete profile and PII
    db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).delete()
    db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).delete()
    # Delete notifications
    db.query(Notification).filter(Notification.doc_id == doc_id).delete()

    # Delete original document from IKM
    if doc.ikm_ref:
        ikm_adapter.delete_document(doc.ikm_ref, filename=doc.original_filename)
    if doc.dms_ref and doc.dms_ref.startswith("ikm://"):
        ikm_adapter.delete_document(doc.dms_ref[6:], filename=doc.original_filename)
    # Also delete by doc_id to clean up any legacy entries
    ikm_adapter.delete_document(doc.doc_id, filename=doc.original_filename)

    # Remove physical original file if exists
    file_path = dms_adapter.get_file_path(doc.dms_ref)
    if file_path and file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            pass

    # Delete document record
    db.delete(doc)

    # Record audit event
    db.add(AuditEvent(
        event_id=f"aud-{uuid.uuid4().hex[:8]}",
        actor_id=current_user.user_id,
        action="delete_resume",
        target_doc_id=doc_id,
        outcome="success",
        metadata_json={"doc_id": doc_id, "filename": doc.original_filename}
    ))

    db.commit()

    try:
        from app.services.ikm_sync_service import invalidate_sync_cooldown
        invalidate_sync_cooldown()
    except Exception:
        pass

    return {"success": True, "message": f"Resume '{doc_id}' deleted successfully."}

@router.post("/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_resumes(
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Deletes multiple candidate resume records and associated files from IKM atomically per record.
    Tracks successes, partial failures, and audit logging.
    """
    if not payload.doc_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No resume IDs provided for bulk deletion."
        )

    deleted_ids = []
    failed_ids = []

    for doc_id in payload.doc_ids:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            failed_ids.append({"doc_id": doc_id, "reason": "Resume record not found."})
            continue

        try:
            # Delete related match results
            db.query(MatchResult).filter(MatchResult.doc_id == doc_id).delete()
            # Delete recruitment actions
            db.query(RecruitmentAction).filter(RecruitmentAction.doc_id == doc_id).delete()
            
            # Delete versions from IKM and DB
            from app.integrations.ikm_adapter import ikm_adapter
            versions = db.query(ResumeVersion).filter(ResumeVersion.doc_id == doc_id).all()
            for v in versions:
                if v.dms_ref and v.dms_ref.startswith("ikm://"):
                    ikm_adapter.delete_document(v.dms_ref[6:], filename=f"{doc_id}_{v.version_id}")
                elif v.dms_ref:
                    ikm_adapter.delete_document(v.dms_ref, filename=f"{doc_id}_{v.version_id}")
            db.query(ResumeVersion).filter(ResumeVersion.doc_id == doc_id).delete()

            # Delete profile and PII
            db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).delete()
            db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).delete()
            # Delete notifications
            db.query(Notification).filter(Notification.doc_id == doc_id).delete()

            # Delete original document from IKM
            if doc.ikm_ref:
                ikm_adapter.delete_document(doc.ikm_ref, filename=doc.original_filename)
            if doc.dms_ref and doc.dms_ref.startswith("ikm://"):
                ikm_adapter.delete_document(doc.dms_ref[6:], filename=doc.original_filename)
            ikm_adapter.delete_document(doc.doc_id, filename=doc.original_filename)

            # Remove physical original file if exists
            file_path = dms_adapter.get_file_path(doc.dms_ref)
            if file_path and file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass

            orig_filename = doc.original_filename
            db.delete(doc)

            # Record audit event
            db.add(AuditEvent(
                event_id=f"aud-{uuid.uuid4().hex[:8]}",
                actor_id=current_user.user_id,
                action="bulk_delete_resume",
                target_doc_id=doc_id,
                outcome="success",
                metadata_json={"doc_id": doc_id, "filename": orig_filename}
            ))

            db.commit()
            deleted_ids.append(doc_id)
        except Exception as e:
            db.rollback()
            failed_ids.append({"doc_id": doc_id, "reason": str(e)})

    try:
        from app.services.ikm_sync_service import invalidate_sync_cooldown
        invalidate_sync_cooldown()
    except Exception:
        pass

    total_deleted = len(deleted_ids)
    is_success = total_deleted > 0 or len(failed_ids) == 0

    if failed_ids and total_deleted > 0:
        msg = f"Partially completed: Deleted {total_deleted} resume(s), but {len(failed_ids)} item(s) failed."
    elif failed_ids:
        msg = f"Bulk deletion failed: {len(failed_ids)} item(s) could not be deleted."
    else:
        msg = f"Successfully deleted {total_deleted} resume record(s)."

    return BulkDeleteResponse(
        success=is_success,
        deleted_count=total_deleted,
        deleted_ids=deleted_ids,
        failed_ids=failed_ids,
        message=msg
    )
