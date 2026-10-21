import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import UploadFile

from app.config import settings
from app.models.entities import Document, CandidateProfile, CandidatePII, RecruitmentAction, AuditEvent
from app.integrations.dms_adapter import dms_adapter
from app.integrations.ikm_adapter import ikm_adapter
from app.integrations.neo4j_repository import neo4j_repository
from app.security.encryption import pii_crypto
from app.security.sanitization import validate_uploaded_file
from app.security.rbac import CurrentUser

class ResumeIngestionService:
    """
    Orchestrates resume ingestion:
    - Multi-file validation
    - Stable opaque doc_id generation
    - Immutable DMS storage
    - PII separation & field encryption
    - Candidate profile extraction & indexing
    - Neo4j graph synchronization
    - Initial workflow action tracking
    - Audit logging
    """

    def _generate_doc_id(self, db: Session) -> str:
        """Generates a stable, unique, opaque document ID (e.g. DOC-1009)."""
        existing_doc_ids = {row[0] for row in db.query(Document.doc_id).all()}
        
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

    async def ingest_single_file(
        self,
        file: UploadFile,
        db: Session,
        actor: CurrentUser
    ) -> Dict[str, Any]:
        filename = file.filename or "resume.pdf"
        try:
            # 1. Validate file extension, size limit
            ext = await validate_uploaded_file(file)
            content = await file.read()
            checksum = dms_adapter.calculate_checksum(content)

            # 2. Check duplicate policy
            existing_doc = db.query(Document).filter(Document.checksum == checksum).first()
            if existing_doc:
                return {
                    "filename": filename,
                    "doc_id": existing_doc.doc_id,
                    "status": "duplicate",
                    "checksum": checksum,
                    "error": f"Duplicate file detected. Already registered under {existing_doc.doc_id}."
                }

            # 3. Generate opaque doc_id and store original in DMS
            doc_id = self._generate_doc_id(db)
            dms_ref, _ = dms_adapter.store_original_file(doc_id, filename, content)

            # 4. Ingest via IKM adapter & extract metadata
            ikm_res = ikm_adapter.ingest_document(doc_id, dms_ref)
            ikm_ref = ikm_res.get("ikm_ref", f"ikm-{doc_id}")
            
            # Extract metadata (skills, experience, etc.) and isolate PII
            extracted = ikm_adapter.extract_metadata(doc_id, dms_ref)
            pii_data = extracted.get("pii", {})
            profile_data = extracted.get("profile", {})
            raw_text = extracted.get("raw_text", "")
            masked_text = extracted.get("masked_text", raw_text)

            # 5. Encrypt PII fields (zero plaintext PII in database or LLM prompts)
            encrypted_pii = pii_crypto.encrypt_pii_dict(pii_data)

            # 6. Persist Document record
            doc_record = Document(
                doc_id=doc_id,
                dms_ref=dms_ref,
                ikm_ref=ikm_ref,
                original_filename=filename,
                mime_type=file.content_type or f"application/{ext}",
                checksum=checksum,
                upload_status="ready",
                uploaded_by=actor.user_id,
                uploaded_at=datetime.now(timezone.utc)
            )
            db.add(doc_record)

            # 7. Persist CandidateProfile (PII-masked text summary protects candidate privacy)
            profile_record = CandidateProfile(
                doc_id=doc_id,
                structured_profile_json=profile_data,
                raw_text_summary=masked_text[:2500],
                profile_status="ready",
                updated_at=datetime.now(timezone.utc)
            )
            db.add(profile_record)

            # 8. Persist CandidatePII (Authenticated Encryption)
            pii_record = CandidatePII(
                doc_id=doc_id,
                name_encrypted=encrypted_pii["name_encrypted"],
                email_encrypted=encrypted_pii["email_encrypted"],
                phone_encrypted=encrypted_pii["phone_encrypted"],
                address_encrypted=encrypted_pii["address_encrypted"],
                updated_at=datetime.now(timezone.utc)
            )
            db.add(pii_record)

            # 9. Track initial workflow recruitment action
            action_record = RecruitmentAction(
                action_id=f"act-{uuid.uuid4().hex[:8]}",
                doc_id=doc_id,
                action_type="uploaded",
                status="pending_review",
                owner_id=actor.user_id,
                notes=f"Uploaded via web application by {actor.name}.",
                action_at=datetime.now(timezone.utc)
            )
            db.add(action_record)

            # 10. Audit event
            audit_record = AuditEvent(
                event_id=f"aud-{uuid.uuid4().hex[:8]}",
                actor_id=actor.user_id,
                action="upload_resume",
                target_doc_id=doc_id,
                outcome="success",
                metadata_json={"filename": filename, "checksum": checksum}
            )
            db.add(audit_record)

            db.commit()

            # 11. Sync structured relationships into Neo4j graph repository
            neo4j_repository.sync_candidate_profile(doc_id, profile_data, dms_ref)

            return {
                "filename": filename,
                "doc_id": doc_id,
                "status": "ready",
                "checksum": checksum,
                "error": None
            }

        except Exception as e:
            db.rollback()
            return {
                "filename": filename,
                "doc_id": None,
                "status": "failed",
                "checksum": None,
                "error": f"Failed to process file: {str(e)}"
            }

    async def ingest_batch(
        self,
        files: List[UploadFile],
        db: Session,
        actor: CurrentUser
    ) -> Dict[str, Any]:
        """
        Processes multiple resumes concurrently.
        Per-file failure resilience: one corrupt file does not abort the batch.
        """
        results = []
        for file in files:
            res = await self.ingest_single_file(file, db, actor)
            results.append(res)

        successful = sum(1 for r in results if r["status"] in ("ready", "uploaded"))
        failed = sum(1 for r in results if r["status"] == "failed")

        return {
            "total_files": len(files),
            "successful_count": successful,
            "failed_count": failed,
            "results": results
        }

resume_ingestion_service = ResumeIngestionService()
