import os
import re
import uuid
import time
import logging
import threading
from typing import Dict, Any, List, Set, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import (
    Document,
    CandidateProfile,
    CandidatePII,
    ResumeVersion,
    MatchResult,
    RecruitmentAction,
    Notification,
    AuditEvent
)
from app.integrations.ikm_adapter import ikm_adapter
from app.integrations.dms_adapter import dms_adapter
from app.security.encryption import pii_crypto

logger = logging.getLogger(__name__)

_sync_lock = threading.Lock()
_last_sync_time: float = 0.0
_last_sync_result: Dict[str, Any] = {"synced": False, "status": "uninitialized"}

def invalidate_sync_cooldown():
    """Resets the sync cooldown so the next request immediately syncs with IKM."""
    global _last_sync_time
    _last_sync_time = 0.0

def _extract_remote_uuid(ref: Optional[str]) -> Optional[str]:
    """Extracts a valid 36-char IKM UUID from references like ikm://<uuid> or raw <uuid>."""
    if not ref:
        return None
    clean = ref.strip()
    if clean.startswith("ikm://"):
        clean = clean[6:]
    if clean.startswith("local-"):
        clean = clean[6:]
    # Check if clean is a standard UUID (36 chars, 4 hyphens)
    if len(clean) == 36 and clean.count("-") == 4:
        return clean.lower()
    return None

def _generate_doc_id(db: Session) -> str:
    """Generates a stable, unique, opaque document ID (e.g. DOC-1001)."""
    existing_doc_ids = {row[0] for row in db.query(Document.doc_id).all()}
    for obj in db.new:
        if isinstance(obj, Document) and obj.doc_id:
            existing_doc_ids.add(obj.doc_id)

    max_num = 1000
    for d_id in existing_doc_ids:
        if d_id and d_id.startswith("DOC-"):
            num_part = d_id[4:]
            if num_part.isdigit():
                max_num = max(max_num, int(num_part))

    next_num = max_num + 1
    while f"DOC-{next_num}" in existing_doc_ids:
        next_num += 1

    return f"DOC-{next_num}"

def sync_ikm_with_database(db: Session, force: bool = False) -> Dict[str, Any]:
    """
    Synchronizes candidate documents bidirectionally with the configured IKM repository:
    1. If a document was deleted in IKM, it is cleanly removed from the local database.
    2. If a document was added in IKM, it is imported into the local database.
    3. Thread-safe with short debounce cooldown to optimize performance.
    """
    global _last_sync_time, _last_sync_result

    now = time.time()
    # Fast cooldown check unless force requested or cache was invalidated
    cache_valid = getattr(ikm_adapter, "_doc_list_cache", None) is not None
    if not force and cache_valid and (now - _last_sync_time < 2.0):
        return _last_sync_result

    with _sync_lock:
        now = time.time()
        cache_valid = getattr(ikm_adapter, "_doc_list_cache", None) is not None
        if not force and cache_valid and (now - _last_sync_time < 2.0):
            return _last_sync_result

        # 1. Authenticate with IKM
        if not ikm_adapter.authenticate():
            _last_sync_result = {
                "synced": False,
                "status": "ikm_offline_or_unauthenticated",
                "message": "IKM adapter could not authenticate. Using existing local state."
            }
            return _last_sync_result

        target_repo = ikm_adapter.repository_id or os.getenv("IKM_REPOSITORY_ID", "1e8d9fd6-d195-4026-8ede-66363f902a3b")
        if not target_repo:
            _last_sync_result = {
                "synced": False,
                "status": "no_repository_configured",
                "message": "No IKM repository ID configured."
            }
            return _last_sync_result

        try:
            # 2. Fetch live documents from IKM repository
            remote_docs = ikm_adapter.list_documents(repository_id=target_repo, force=True, limit=500)
            remote_docs_by_id: Dict[str, Dict[str, Any]] = {}
            for d in remote_docs:
                r_id = d.get("document_id")
                if r_id:
                    remote_docs_by_id[r_id.lower()] = d

            remote_uuids: Set[str] = set(remote_docs_by_id.keys())
            remote_filenames: Set[str] = {
                (d.get("original_file_name") or d.get("document_name") or "").lower().strip()
                for d in remote_docs_by_id.values()
                if (d.get("original_file_name") or d.get("document_name"))
            }

            # 3. Scan local database for deleted IKM documents
            local_docs = db.query(Document).all()
            deleted_doc_ids: List[str] = []
            tracked_local_uuids: Set[str] = set()

            for doc in local_docs:
                remote_uuid = _extract_remote_uuid(doc.ikm_ref) or _extract_remote_uuid(doc.dms_ref)
                if not remote_uuid and doc.original_filename:
                    # Match by filename against remote docs
                    fn_low = doc.original_filename.lower().strip()
                    for r_u, r_info in remote_docs_by_id.items():
                        r_fn = (r_info.get("original_file_name") or r_info.get("document_name") or "").lower().strip()
                        if r_fn == fn_low:
                            remote_uuid = r_u
                            doc.ikm_ref = f"ikm://{r_u}"
                            doc.dms_ref = f"ikm://{r_u}"
                            break

                is_present_in_ikm = False
                if remote_uuid:
                    if remote_uuid in remote_uuids:
                        is_present_in_ikm = True
                        tracked_local_uuids.add(remote_uuid)
                elif doc.original_filename:
                    fn_low = doc.original_filename.lower().strip()
                    if fn_low in remote_filenames:
                        is_present_in_ikm = True

                if not is_present_in_ikm:
                    # Remote file was deleted in IKM! Delete from local application
                    doc_id = doc.doc_id
                    db.query(MatchResult).filter(MatchResult.doc_id == doc_id).delete()
                    db.query(RecruitmentAction).filter(RecruitmentAction.doc_id == doc_id).delete()
                    db.query(ResumeVersion).filter(ResumeVersion.doc_id == doc_id).delete()
                    db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).delete()
                    db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).delete()
                    db.query(Notification).filter(Notification.doc_id == doc_id).delete()

                    # Remove physical file if present
                    file_path = dms_adapter.get_file_path(doc.dms_ref)
                    if file_path and file_path.exists():
                        try:
                            file_path.unlink()
                        except Exception:
                            pass

                    db.delete(doc)
                    deleted_doc_ids.append(doc_id)

                    db.add(AuditEvent(
                        event_id=f"aud-{uuid.uuid4().hex[:8]}",
                        actor_id="system:ikm_sync",
                        action="delete_resume_ikm_sync",
                        target_doc_id=doc_id,
                        metadata_json={"reason": "Document deleted in remote IKM repository", "ikm_ref": remote_uuid or doc.ikm_ref}
                    ))

            # 4. Check for remote documents added in IKM that are not yet in local DB
            imported_doc_ids: List[str] = []
            for r_uuid, r_info in remote_docs_by_id.items():
                if r_uuid not in tracked_local_uuids:
                    fn = (r_info.get("original_file_name") or r_info.get("document_name") or f"{r_uuid}.docx").strip()
                    # Check if local DB already has a document matching this filename or IKM ref to prevent duplicates
                    existing_doc = db.query(Document).filter(
                        (Document.original_filename.ilike(fn)) |
                        (Document.ikm_ref == f"ikm://{r_uuid}") |
                        (Document.ikm_ref == r_uuid) |
                        (Document.dms_ref == f"ikm://{r_uuid}")
                    ).first()
                    if existing_doc:
                        existing_doc.ikm_ref = f"ikm://{r_uuid}"
                        existing_doc.dms_ref = f"ikm://{r_uuid}"
                        tracked_local_uuids.add(r_uuid)
                        continue

                    # Attempt to download and register document
                    dl_bytes = ikm_adapter.download_document(r_uuid)
                    if dl_bytes:
                        checksum = dms_adapter.calculate_checksum(dl_bytes)
                        existing_by_checksum = db.query(Document).filter(Document.checksum == checksum).first()
                        if existing_by_checksum:
                            existing_by_checksum.ikm_ref = f"ikm://{r_uuid}"
                            existing_by_checksum.dms_ref = f"ikm://{r_uuid}"
                            tracked_local_uuids.add(r_uuid)
                            continue

                        new_doc_id = _generate_doc_id(db)
                        extracted = ikm_adapter.extract_metadata(new_doc_id, dl_bytes, filename=fn)
                        pii_data = extracted.get("pii", {})
                        profile_data = extracted.get("profile", {})
                        raw_text = extracted.get("raw_text", "")
                        masked_text = extracted.get("masked_text", raw_text)
                        encrypted_pii = pii_crypto.encrypt_pii_dict(pii_data)

                        ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else "bin"
                        mime = "application/pdf" if ext == "pdf" else ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == "docx" else "text/plain")

                        new_doc = Document(
                            doc_id=new_doc_id,
                            dms_ref=f"ikm://{r_uuid}",
                            ikm_ref=f"ikm://{r_uuid}",
                            original_filename=fn,
                            mime_type=mime,
                            checksum=checksum,
                            upload_status="ready",
                            uploaded_by="ikm_sync",
                            uploaded_at=datetime.now(timezone.utc)
                        )
                        db.add(new_doc)

                        prof = CandidateProfile(
                            doc_id=new_doc_id,
                            structured_profile_json=profile_data,
                            raw_text_summary=masked_text[:2500],
                            profile_status="ready",
                            updated_at=datetime.now(timezone.utc)
                        )
                        db.add(prof)

                        pii = CandidatePII(
                            doc_id=new_doc_id,
                            **encrypted_pii
                        )
                        db.add(pii)

                        db.add(RecruitmentAction(
                            action_id=f"act-{uuid.uuid4().hex[:8]}",
                            doc_id=new_doc_id,
                            action_type="synced_from_ikm",
                            status="pending_review",
                            owner_id="system",
                            action_at=datetime.now(timezone.utc),
                            notes=f"Document imported from IKM repository ({r_uuid})."
                        ))

                        # Sync with Neo4j if enabled
                        try:
                            from app.integrations.neo4j_repository import neo4j_repository
                            neo4j_repository.sync_candidate_profile(new_doc_id, profile_data, f"ikm://{r_uuid}")
                        except Exception:
                            pass

                        imported_doc_ids.append(new_doc_id)
                        tracked_local_uuids.add(r_uuid)

            if deleted_doc_ids or imported_doc_ids:
                db.commit()

            _last_sync_time = time.time()
            _last_sync_result = {
                "synced": True,
                "repository_id": target_repo,
                "remote_count": len(remote_uuids),
                "deleted_count": len(deleted_doc_ids),
                "deleted_ids": deleted_doc_ids,
                "imported_count": len(imported_doc_ids),
                "imported_ids": imported_doc_ids
            }
            return _last_sync_result

        except Exception as e:
            logger.error(f"Error during IKM synchronization: {e}", exc_info=True)
            _last_sync_result = {
                "synced": False,
                "error": str(e)
            }
            return _last_sync_result
