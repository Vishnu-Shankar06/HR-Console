import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.config import settings
from app.models.entities import Document, CandidateProfile, CandidatePII, JobDescription, ResumeVersion, AuditEvent, RecruitmentAction
from app.integrations.llm_adapter import llm_adapter
from app.integrations.dms_adapter import dms_adapter
from app.services.scoring_service import scoring_service
from app.security.rbac import CurrentUser

class ResumeImprovementService:
    """
    Resume improvement service:
    - Evidence-grounded gap analysis
    - Concrete rewrite recommendations with confirmation flags
    - Transparent alignment scoring (never promising a 90% ATS guarantee)
    - Versioned document generation preserving original files intact
    """

    def analyze_resume_for_job(
        self,
        doc_id: str,
        db: Session,
        actor: CurrentUser,
        job_id: Optional[str] = None,
        job_text: Optional[str] = None,
        personal_overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate resume '{doc_id}' not found."
            )

        profile_record = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
        if not profile_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Candidate profile for '{doc_id}' is not yet processed."
            )

        profile = profile_record.structured_profile_json
        original_text = profile_record.raw_text_summary or ""

        # Resolve Job Requirements
        job_title = "Target Position"
        if job_id:
            job_rec = db.query(JobDescription).filter(JobDescription.job_id == job_id).first()
            if not job_rec:
                raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
            jd_reqs = job_rec.requirements_json
            job_title = job_rec.title
        elif job_text and job_text.strip():
            jd_reqs = llm_adapter.parse_job_description(job_text)
            job_title = jd_reqs.get("title", "Target Position")
        else:
            raise HTTPException(status_code=400, detail="Must provide either job_id or job_text.")

        # Compute internal alignment score
        score_data = scoring_service.calculate_score(jd_reqs, profile)
        alignment_score = score_data["total_score"]

        # Generate improvements
        improvements = llm_adapter.generate_resume_improvements(jd_reqs, profile, original_text)

        # Resolve authentic candidate personal details
        overrides = personal_overrides or {}
        cand_name = overrides.get("name")
        cand_role = overrides.get("role") or job_title
        cand_phone = overrides.get("phone")
        cand_email = overrides.get("email")
        cand_loc = overrides.get("location")
        cand_links = overrides.get("links")

        pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
        if pii_rec:
            from app.security.encryption import pii_crypto
            decrypted = pii_crypto.decrypt_pii_dict({
                "name_encrypted": pii_rec.name_encrypted,
                "email_encrypted": pii_rec.email_encrypted,
                "phone_encrypted": pii_rec.phone_encrypted,
                "address_encrypted": pii_rec.address_encrypted
            })
            if not cand_name:
                cand_name = decrypted.get("name")
            if not cand_email:
                cand_email = decrypted.get("email")
            if not cand_phone:
                cand_phone = decrypted.get("phone")
            if not cand_loc:
                cand_loc = decrypted.get("address")

        cand_name = self._resolve_clean_candidate_name(cand_name, doc.original_filename)

        # If user explicitly provided new personal contact details in UI, persist to CandidatePII
        if overrides.get("email") or overrides.get("phone") or overrides.get("location") or overrides.get("name"):
            from app.security.encryption import pii_crypto
            if pii_rec:
                if overrides.get("email"):
                    pii_rec.email_encrypted = pii_crypto.encrypt_field(overrides["email"].strip())
                if overrides.get("phone"):
                    pii_rec.phone_encrypted = pii_crypto.encrypt_field(overrides["phone"].strip())
                if overrides.get("location"):
                    pii_rec.address_encrypted = pii_crypto.encrypt_field(overrides["location"].strip())
                if overrides.get("name"):
                    pii_rec.name_encrypted = pii_crypto.encrypt_field(cand_name)
                db.commit()

        personal_details_dict = {
            "name": cand_name,
            "role": cand_role,
            "phone": cand_phone or "",
            "email": cand_email or "",
            "location": cand_loc or "",
            "links": cand_links or ""
        }

        # Call Grok LLM Adapter to generate substantive, evidence-grounded resume improvements
        from app.integrations.grok_adapter import grok_adapter
        grok_result = grok_adapter.improve_resume(
            candidate_name=cand_name,
            raw_text=original_text,
            profile=profile,
            jd_reqs=jd_reqs,
            target_role=job_title,
            gaps=improvements.get("gaps", []),
            matched=improvements.get("matched_requirements", []),
            personal_details_override=personal_details_dict
        )

        # Audit event
        db.add(AuditEvent(
            event_id=f"aud-{uuid.uuid4().hex[:8]}",
            actor_id=actor.user_id,
            action="resume_improvement_analysis",
            target_doc_id=doc_id,
            outcome="success",
            metadata_json={"job_id": job_id, "score": alignment_score, "llm": grok_result.get("model_used")}
        ))
        db.commit()

        return {
            "doc_id": doc_id,
            "job_id": job_id,
            "job_title": job_title,
            "internal_match_score": alignment_score,
            "score_disclaimer": (
                "Internal alignment score based on documented evidence. "
                "Different ATS systems use different parsing algorithms; this score is an internal diagnostic benchmark."
            ),
            "matched_requirements": improvements["matched_requirements"],
            "partially_demonstrated": [
                {"requirement": g["requirement"], "reason": g["recommendation"]}
                for g in improvements["gaps"] if g.get("status") == "partially_demonstrated"
            ],
            "not_demonstrated": [
                g for g in improvements["gaps"] if g.get("status") == "not_demonstrated"
            ],
            "formatting_issues": improvements["formatting_issues"],
            "suggested_rewrites": grok_result.get("suggested_rewrites") or improvements["suggested_rewrites"],
            "original_text_preview": original_text,
            "improved_resume_text": grok_result.get("improved_resume_text"),
            "change_summary": grok_result.get("change_summary"),
            "key_enhancements": grok_result.get("key_enhancements"),
            "candidate_personal_details": personal_details_dict,
            "llm_model": grok_result.get("model_used")
        }

    def _resolve_clean_candidate_name(self, raw_name: Optional[str], filename: str) -> str:
        invalid_names = {"SUMMARY", "OBJECTIVE", "PROFILE", "RESUME", "CURRICULUM VITAE", "CV", "CANDIDATE", "PROFESSIONAL SUMMARY"}
        if raw_name and raw_name.strip() and raw_name.strip().upper() not in invalid_names and not raw_name.strip().lower().startswith("candidate"):
            return raw_name.strip()
        
        # Clean from filename
        clean = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc|txt)$', '', filename, flags=re.IGNORECASE)
        clean = re.sub(r'[\-_]+', ' ', clean).strip()
        words = clean.split()
        clean_words = [w for w in words if w.lower() not in ['resume', 'cv', 'final', 'resumee', 'sfdc', 'developer', 'engineer', 'vault', 'qmsqdocs', 'qa', 'salesforce', 'se']]
        if clean_words:
            return ' '.join(clean_words).title()
        return clean.title() if clean else "Candidate Professional"

    def save_revised_version(
        self,
        doc_id: str,
        change_summary: str,
        revised_content: str,
        db: Session,
        actor: CurrentUser,
        approved: bool = True,
        personal_overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Stores an approved revised resume draft as a new version in DMS,
        leaving the original file completely untouched.
        """
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

        # Calculate version sequence
        existing_versions_count = db.query(ResumeVersion).filter(ResumeVersion.doc_id == doc_id).count()
        next_ver_num = existing_versions_count + 1
        version_id = f"VER-{doc_id}-v{next_ver_num}"

        # Resolve candidate name & profile
        cand_name = doc.original_filename.rsplit(".", 1)[0]
        pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
        if pii_rec and pii_rec.name_encrypted:
            from app.security.encryption import pii_crypto
            decrypted = pii_crypto.decrypt_pii_dict({"name_encrypted": pii_rec.name_encrypted})
            if decrypted.get("name"):
                cand_name = decrypted["name"]

        cand_name = self._resolve_clean_candidate_name(cand_name, doc.original_filename)

        if personal_overrides and personal_overrides.get("name"):
            clean_override = str(personal_overrides["name"]).strip()
            if clean_override.upper() not in ["SUMMARY", "OBJECTIVE", "PROFILE", "RESUME"]:
                cand_name = clean_override

        # Encrypt & persist any recruiter-supplied contact details in CandidatePII
        if personal_overrides and any(personal_overrides.get(k) for k in ["name", "email", "phone", "location"]):
            from app.security.encryption import pii_crypto
            existing_pii = {}
            if pii_rec:
                existing_pii = pii_crypto.decrypt_pii_dict({
                    "name_encrypted": pii_rec.name_encrypted,
                    "email_encrypted": pii_rec.email_encrypted,
                    "phone_encrypted": pii_rec.phone_encrypted,
                    "address_encrypted": pii_rec.address_encrypted
                })
            updated_dict = {
                "name": cand_name,
                "email": personal_overrides.get("email") or existing_pii.get("email") or "",
                "phone": personal_overrides.get("phone") or existing_pii.get("phone") or "",
                "address": personal_overrides.get("location") or existing_pii.get("address") or ""
            }
            enc_dict = pii_crypto.encrypt_pii_dict(updated_dict)
            if pii_rec:
                pii_rec.name_encrypted = enc_dict["name_encrypted"]
                pii_rec.email_encrypted = enc_dict["email_encrypted"]
                pii_rec.phone_encrypted = enc_dict["phone_encrypted"]
                pii_rec.address_encrypted = enc_dict["address_encrypted"]
            else:
                db.add(CandidatePII(
                    doc_id=doc_id,
                    name_encrypted=enc_dict["name_encrypted"],
                    email_encrypted=enc_dict["email_encrypted"],
                    phone_encrypted=enc_dict["phone_encrypted"],
                    address_encrypted=enc_dict["address_encrypted"]
                ))
            db.flush()


        profile_rec = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
        profile = profile_rec.structured_profile_json if profile_rec else {}
        orig_path = dms_adapter.get_file_path(doc.dms_ref)

        # Generate professional Word (.docx) file
        from app.services.word_resume_service import word_resume_service
        target_role = "Senior Technical Professional"
        if change_summary and "for " in change_summary.lower():
            target_role = change_summary.split("for ")[-1].strip()

        docx_path = word_resume_service.generate_improved_docx(
            doc_id=doc_id,
            version_id=version_id,
            candidate_name=cand_name,
            target_role=target_role,
            profile=profile,
            revised_content=revised_content,
            original_doc_path=orig_path
        )
        dms_ref = str(docx_path.relative_to(settings.BASE_DIR)).replace("\\", "/")

        # Persist version record
        version_record = ResumeVersion(
            version_id=version_id,
            doc_id=doc_id,
            dms_ref=dms_ref,
            parent_version_id=f"VER-{doc_id}-v{existing_versions_count}" if existing_versions_count > 0 else None,
            created_by=actor.user_id,
            approved_by=actor.user_id if approved else None,
            created_at=datetime.now(timezone.utc),
            change_summary=change_summary,
            revised_content=revised_content
        )
        db.add(version_record)

        # Record recruitment action
        act_record = RecruitmentAction(
            action_id=f"act-{uuid.uuid4().hex[:8]}",
            doc_id=doc_id,
            action_type="improved",
            status="reviewed",
            owner_id=actor.user_id,
            notes=f"Created revised resume version {version_id}: {change_summary}",
            action_at=datetime.now(timezone.utc)
        )
        db.add(act_record)

        # Audit event
        db.add(AuditEvent(
            event_id=f"aud-{uuid.uuid4().hex[:8]}",
            actor_id=actor.user_id,
            action="create_resume_version",
            target_doc_id=doc_id,
            outcome="success",
            metadata_json={"version_id": version_id, "dms_ref": dms_ref}
        ))

        db.commit()

        return {
            "version_id": version_id,
            "doc_id": doc_id,
            "parent_version_id": version_record.parent_version_id,
            "created_at": version_record.created_at,
            "created_by": version_record.created_by,
            "approved_by": version_record.approved_by,
            "change_summary": change_summary,
            "dms_ref": dms_ref
        }

    def list_versions(self, doc_id: str, db: Session) -> List[Dict[str, Any]]:
        versions = (
            db.query(ResumeVersion)
            .filter(ResumeVersion.doc_id == doc_id)
            .order_by(ResumeVersion.created_at.desc())
            .all()
        )
        return [
            {
                "version_id": v.version_id,
                "doc_id": v.doc_id,
                "parent_version_id": v.parent_version_id,
                "created_at": v.created_at,
                "created_by": v.created_by,
                "approved_by": v.approved_by,
                "change_summary": v.change_summary,
                "dms_ref": v.dms_ref,
                "revised_content": v.revised_content
            }
            for v in versions
        ]

resume_improvement_service = ResumeImprovementService()
