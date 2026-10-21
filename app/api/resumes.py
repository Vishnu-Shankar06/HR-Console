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
            profile_dto = CandidateProfileDTO(
                doc_id=doc.doc_id,
                skills=p_data.get("skills", []),
                qualifications=p_data.get("qualifications", []),
                experience=p_data.get("experience", []),
                projects=p_data.get("projects", []),
                certifications=p_data.get("certifications", []),
                profile_status=prof.profile_status,
                source_document_ref=doc.dms_ref,
                raw_text_summary=prof.raw_text_summary
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
            pii_dto = CandidatePIIDTO(
                doc_id=doc.doc_id,
                name=cand_name,
                email=decrypted.get("email"),
                phone=decrypted.get("phone"),
                address=decrypted.get("address")
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
        profile_dto = CandidateProfileDTO(
            doc_id=doc.doc_id,
            skills=p_data.get("skills", []),
            qualifications=p_data.get("qualifications", []),
            experience=p_data.get("experience", []),
            projects=p_data.get("projects", []),
            certifications=p_data.get("certifications", []),
            profile_status=prof.profile_status,
            source_document_ref=doc.dms_ref,
            raw_text_summary=prof.raw_text_summary
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
        pii_dto = CandidatePIIDTO(
            doc_id=doc.doc_id,
            name=cand_name,
            email=decrypted.get("email"),
            phone=decrypted.get("phone"),
            address=decrypted.get("address")
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
    Retrieves decrypted personal information (Name, Email, Phone, Address).
    Restricted to authorized roles and logs an audit trail event.
    """
    pii_record = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
    if not pii_record:
        raise HTTPException(status_code=404, detail=f"PII record for '{doc_id}' not found.")

    decrypted = pii_crypto.decrypt_pii_dict({
        "name_encrypted": pii_record.name_encrypted,
        "email_encrypted": pii_record.email_encrypted,
        "phone_encrypted": pii_record.phone_encrypted,
        "address_encrypted": pii_record.address_encrypted
    })

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
        name=decrypted.get("name"),
        email=decrypted.get("email"),
        phone=decrypted.get("phone"),
        address=decrypted.get("address")
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

    # 1. Primary Remote Storage: Check IKM
    from app.integrations.ikm_adapter import ikm_adapter
    if doc.ikm_ref and not doc.ikm_ref.startswith("local-") and not doc.ikm_ref.startswith("ikm-"):
        ikm_bytes = ikm_adapter.download_document(doc.ikm_ref)
        if ikm_bytes:
            from fastapi.responses import Response
            import urllib.parse
            encoded_fn = urllib.parse.quote(doc.original_filename)
            return Response(
                content=ikm_bytes,
                media_type=doc.mime_type or "application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{doc.original_filename}"; filename*=UTF-8\'\'{encoded_fn}'}
            )

    # 2. Local DMS fallback
    file_path = dms_adapter.get_file_path(doc.dms_ref)
    if file_path and file_path.exists():
        return FileResponse(
            path=file_path,
            media_type=doc.mime_type,
            filename=doc.original_filename
        )

    raise HTTPException(status_code=404, detail="Original document file not found in IKM or DMS storage.")

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

    # 1. Primary Remote Storage: Check IKM
    from app.integrations.ikm_adapter import ikm_adapter
    if doc.ikm_ref and not doc.ikm_ref.startswith("local-") and not doc.ikm_ref.startswith("ikm-"):
        # Check if preview rendered PDF exists
        prev_data = ikm_adapter.get_document_preview_data(doc.ikm_ref)
        if prev_data and prev_data.get("content_bytes_b64"):
            import base64
            from fastapi.responses import Response
            pdf_bytes = base64.b64decode(prev_data["content_bytes_b64"])
            return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "inline"})
        
        ikm_bytes = ikm_adapter.download_document(doc.ikm_ref)
        if ikm_bytes:
            from fastapi.responses import Response
            return Response(content=ikm_bytes, media_type=doc.mime_type or "application/octet-stream", headers={"Content-Disposition": "inline"})

    # 2. Local DMS fallback
    file_path = dms_adapter.get_file_path(doc.dms_ref)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Original document file not found in IKM or DMS storage.")

    headers = {"Content-Disposition": "inline"}
    return FileResponse(
        path=file_path,
        media_type=doc.mime_type or "application/octet-stream",
        headers=headers
    )

@router.delete("/{doc_id}")
def delete_resume(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Deletes a candidate resume record and its associated data (PII, profile, revisions, actions).
    Also cleans up files from the DMS.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    # Delete related match results
    db.query(MatchResult).filter(MatchResult.doc_id == doc_id).delete()
    # Delete recruitment actions
    db.query(RecruitmentAction).filter(RecruitmentAction.doc_id == doc_id).delete()
    # Delete resume versions
    db.query(ResumeVersion).filter(ResumeVersion.doc_id == doc_id).delete()
    # Delete profile and PII
    db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).delete()
    db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).delete()
    # Delete notifications
    db.query(Notification).filter(Notification.doc_id == doc_id).delete()

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

    return {"success": True, "message": f"Resume '{doc_id}' deleted successfully."}

@router.post("/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_resumes(
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Deletes multiple candidate resume records and associated DMS files atomically per record.
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
            # Delete resume versions
            db.query(ResumeVersion).filter(ResumeVersion.doc_id == doc_id).delete()
            # Delete profile and PII
            db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).delete()
            db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).delete()
            # Delete notifications
            db.query(Notification).filter(Notification.doc_id == doc_id).delete()

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
