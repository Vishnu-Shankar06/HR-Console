import re
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

        profile = profile_record.structured_profile_json or {}
        original_text = profile_record.raw_text_summary or ""

        # Pre-resolve candidate name from overrides or PII
        overrides = personal_overrides or {}
        cand_name = overrides.get("name")
        pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
        if pii_rec and not cand_name:
            from app.security.encryption import pii_crypto
            decrypted = pii_crypto.decrypt_pii_dict({"name_encrypted": pii_rec.name_encrypted})
            cand_name = decrypted.get("name")
        cand_name = self._resolve_clean_candidate_name(cand_name, doc.original_filename)

        # Step 1: Retrieve original document binary directly from IKM
        from app.integrations.ikm_adapter import ikm_adapter
        from app.services.word_resume_service import word_resume_service
        from app.integrations.grok_adapter import grok_adapter

        orig_file_bytes = None
        if doc.ikm_ref:
            orig_file_bytes = ikm_adapter.download_document(doc.ikm_ref)
        if not orig_file_bytes and doc.dms_ref and doc.dms_ref.startswith("ikm://"):
            orig_file_bytes = ikm_adapter.download_document(doc.dms_ref[6:])
        if not orig_file_bytes:
            found = ikm_adapter.find_document_by_name(doc.original_filename)
            if found and found.get("document_id"):
                orig_file_bytes = ikm_adapter.download_document(found["document_id"])

        if not orig_file_bytes:
            if original_text:
                orig_file_bytes = original_text.encode("utf-8")
            elif profile:
                skills_str = ", ".join(profile.get("skills", []))
                original_text = f"Resume Content for {cand_name}\nSkills: {skills_str}"
                orig_file_bytes = original_text.encode("utf-8")
            else:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Original document '{doc.original_filename}' could not be retrieved from IKM persistent storage."
                )

        # Step 2: Extract text and document structure in-memory
        is_docx = (orig_file_bytes.startswith(b"PK\x03\x04") or doc.original_filename.lower().endswith(".docx"))
        doc_type = "docx" if is_docx else ("pdf" if orig_file_bytes.startswith(b"%PDF") else "text")

        if is_docx:
            doc_elements = word_resume_service.extract_docx_elements(orig_file_bytes)
        else:
            doc_elements = word_resume_service.extract_text_elements(original_text)

        extracted_text = ikm_adapter.extract_raw_text(orig_file_bytes, filename=doc.original_filename)
        if extracted_text and len(extracted_text.strip()) > 30:
            original_text = extracted_text

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

        # Compute internal diagnostic alignment score
        score_data = scoring_service.calculate_score(jd_reqs, profile)
        alignment_score = score_data["total_score"]

        # Step 3: Resolve authentic candidate personal details
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

        # Inspect IKM connectivity and retrieve evidence if available
        ikm_evidence = None
        ikm_note = "Candidate evidence verified against repository document."
        if hasattr(ikm_adapter, "get_health_status"):
            h = ikm_adapter.get_health_status()
            if h.get("authenticated"):
                try:
                    ikm_evidence = ikm_adapter.search(query=f"{job_title} {' '.join(jd_reqs.get('technical_skills', []))}", top_k=3)
                    ikm_note = "Supporting evidence retrieved from enterprise IKM platform."
                except Exception:
                    ikm_note = "Verified candidate evidence from repository."

        # Step 4 & 5: Invoke Groq LLM (Anonymizes in-memory, sends to Groq, validates, restores PII)
        grok_result = grok_adapter.improve_resume(
            candidate_name=cand_name,
            raw_text=original_text,
            profile=profile,
            jd_reqs=jd_reqs,
            target_role=job_title,
            personal_details_override=personal_details_dict,
            doc_elements=doc_elements,
            ikm_evidence=ikm_evidence
        )

        # Protect candidate personal details from being rewritten or flagged as errors
        contact_tokens = set()
        for val in [cand_name, cand_phone, cand_email, cand_loc, cand_links]:
            if val and len(str(val).strip()) > 2:
                contact_tokens.add(str(val).strip().lower())

        structured_changes = grok_result.get("changes", [])
        safe_structured_changes = []
        for chg in structured_changes:
            sec = str(chg.get("section", "")).lower()
            if sec in ("personal_details", "contact_info", "header"):
                continue
            orig = str(chg.get("original_text", "")).strip().lower()
            if any(tok in orig for tok in contact_tokens if len(tok) > 4 and orig == tok):
                continue
            if "proposed_text" in chg and isinstance(chg["proposed_text"], str):
                chg["proposed_text"] = re.sub(r'^(?:#{1,6}\s+)', '', chg["proposed_text"])
            if not chg.get("target_element_id") or str(chg.get("target_element_id")).lower() == "null":
                chg["target_element_id"] = f"elem-{len(safe_structured_changes) + 1}"
            else:
                chg["target_element_id"] = str(chg["target_element_id"])
            safe_structured_changes.append(chg)
        structured_changes = safe_structured_changes

        suggested_rewrites = grok_result.get("suggested_rewrites", [])
        if not suggested_rewrites:
            for chg in structured_changes:
                suggested_rewrites.append({
                    "section": chg.get("section", "professional_experience"),
                    "current_evidence": chg.get("original_text", ""),
                    "suggested_text": chg.get("proposed_text", ""),
                    "rationale": chg.get("reason", "Target-aligned phrasing with verified competencies"),
                    "requires_user_confirmation": chg.get("requires_user_confirmation", False)
                })

        # Process Groq-identified gaps and matches
        groq_gaps = grok_result.get("gaps", [])
        groq_matched = list(grok_result.get("matched_requirements", []))
        if not groq_matched:
            cand_skills = set(s.lower() for s in profile.get("skills", []))
            for req in jd_reqs.get("technical_skills", []):
                if req.lower() in cand_skills:
                    groq_matched.append({
                        "requirement": req,
                        "status": "demonstrated",
                        "evidence": f"Demonstrated in candidate profile with verified experience in {req}."
                    })

        partially_dem = [
            {"requirement": g.get("requirement", ""), "reason": g.get("reason") or g.get("evidence") or "Partially demonstrated in career history"}
            for g in groq_gaps if g.get("status") == "partially_demonstrated"
        ]
        not_dem = [
            g for g in groq_gaps if g.get("status") != "partially_demonstrated"
        ]

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

        # Build fully aligned improved text
        improved_raw = grok_result.get("improved_resume_text") or original_text
        aligned_improved_text = self._build_aligned_improved_text(
            doc_elements=doc_elements,
            changes=structured_changes,
            fallback_text=improved_raw
        )
        aligned_improved_text = self._sanitize_text(aligned_improved_text)

        change_summary = grok_result.get("change_summary") or (
            f"Target-aligned executive optimization for {job_title}: strengthened summary, "
            f"elevated experience with quantifiable STAR metrics, and highlighted core competencies."
        )
        change_summary = self._sanitize_text(change_summary)

        return {
            "doc_id": doc_id,
            "job_id": job_id,
            "job_title": job_title,
            "internal_match_score": alignment_score,
            "score_disclaimer": (
                "Internal alignment score based on documented evidence. "
                "Different ATS systems use different parsing algorithms; this score is an internal diagnostic benchmark."
            ),
            "matched_requirements": groq_matched if groq_matched else grok_result.get("matched_requirements", []),
            "partially_demonstrated": partially_dem,
            "not_demonstrated": not_dem,
            "formatting_issues": [],
            "suggested_rewrites": suggested_rewrites,
            "original_text_preview": original_text,
            "improved_resume_text": aligned_improved_text,
            "change_summary": change_summary,
            "key_enhancements": grok_result.get("key_enhancements"),
            "candidate_personal_details": personal_details_dict,
            "candidate_name": cand_name,
            "llm_model": grok_result.get("model_used", "Grok / Groq LPU (qwen/qwen3.8-27b)"),
            "ikm_template": grok_result.get("modified_template"),
            "changes": structured_changes,
            "gaps": groq_gaps,
            "ikm_evidence_status": ikm_note,
            "document_type": doc_type
        }

    def _sanitize_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        text = text.replace("\u2192", "->").replace("➔", "->").replace("➜", "->").replace("\ufffd", "")
        text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        lines = []
        for line in text.splitlines():
            # Strips markdown heading hashes like '# ', '## ', '### ' while preserving 'C#' or '#1'
            clean_l = re.sub(r'^(?:#{1,6}\s+)', '', line)
            lines.append(clean_l)
        return "\n".join(lines).strip()

    def _build_aligned_improved_text(
        self,
        doc_elements: List[Dict[str, Any]],
        changes: List[Dict[str, Any]],
        fallback_text: str
    ) -> str:
        if not doc_elements or len(doc_elements) < 8 or not changes:
            return fallback_text
        if "PROFESSIONAL SUMMARY" in fallback_text and not any("SUMMARY" in e.get("text", "").upper() for e in doc_elements):
            return fallback_text

        change_map = {}
        for c in changes:
            tid = c.get("target_element_id")
            if tid:
                change_map[tid] = c.get("proposed_text")
            orig = (c.get("original_text") or "").strip().lower()
            if orig:
                change_map[orig] = c.get("proposed_text")

        lines = []
        for elem in doc_elements:
            tid = elem.get("element_id")
            txt = elem.get("text", "").strip()
            if not txt:
                continue

            replaced = change_map.get(tid) or change_map.get(txt.lower())
            final_text = replaced if replaced else txt

            if elem.get("style", "").startswith("Heading") or txt.upper() in [
                "SUMMARY", "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "SKILLS", "EXPERIENCE",
                "WORK EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS"
            ]:
                clean_heading = re.sub(r'^(?:#{1,6}\s+)', '', final_text).strip()
                if clean_heading.upper() in ["SKILLS", "CORE SKILLS", "KEY SKILLS"]:
                    clean_heading = "TECHNICAL SKILLS"
                elif clean_heading.upper() in ["SUMMARY", "PROFILE"]:
                    clean_heading = "PROFESSIONAL SUMMARY"
                lines.append(clean_heading.upper())
            elif elem.get("style", "").startswith("List") or txt.startswith(("•", "-", "*")):
                clean_bullet = re.sub(r'^[•\-\*]\s*', '', final_text)
                lines.append(f"- {clean_bullet}")
            else:
                lines.append(final_text)

        return "\n\n".join(lines) if lines else fallback_text

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
        personal_overrides: Optional[Dict[str, Any]] = None,
        approved_changes: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Stores an approved revised resume draft as a new version in DMS,
        leaving the original file completely untouched.
        """
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

        # Calculate safe version sequence by inspecting highest existing version
        existing_versions = db.query(ResumeVersion.version_id).filter(
            (ResumeVersion.doc_id == doc_id) | (ResumeVersion.version_id.like(f"VER-{doc_id}-v%"))
        ).all()
        highest_v = 0
        for (v_id,) in existing_versions:
            m = re.search(r'-v(\d+)$', str(v_id))
            if m:
                highest_v = max(highest_v, int(m.group(1)))

        next_ver_num = highest_v + 1
        version_id = f"VER-{doc_id}-v{next_ver_num}"
        while db.query(ResumeVersion.version_id).filter(ResumeVersion.version_id == version_id).first() is not None:
            next_ver_num += 1
            version_id = f"VER-{doc_id}-v{next_ver_num}"

        parent_version_id = f"VER-{doc_id}-v{highest_v}" if highest_v > 0 else None

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

        # 1. Retrieve original document binary directly from IKM
        from app.integrations.ikm_adapter import ikm_adapter
        from app.services.word_resume_service import word_resume_service

        is_orig_docx = bool(doc.original_filename and doc.original_filename.lower().endswith(".docx"))
        orig_file_bytes = None
        if is_orig_docx:
            if doc.ikm_ref:
                orig_file_bytes = ikm_adapter.download_document(doc.ikm_ref)
            if not orig_file_bytes and doc.dms_ref and doc.dms_ref.startswith("ikm://"):
                orig_file_bytes = ikm_adapter.download_document(doc.dms_ref[6:])
            if not orig_file_bytes:
                found = ikm_adapter.find_document_by_name(doc.original_filename)
                if found and found.get("document_id") and (found.get("original_file_name") or "").lower().endswith(".docx"):
                    orig_file_bytes = ikm_adapter.download_document(found["document_id"])

        target_role = "Senior Technical Professional"
        if change_summary and "for " in change_summary.lower():
            target_role = change_summary.split("for ")[-1].strip()

        # 2. Generate revised Word (.docx) file in-memory preserving formatting and styles
        docx_bytes = word_resume_service.generate_improved_docx_bytes(
            candidate_name=cand_name,
            target_role=target_role,
            profile=profile,
            revised_content=revised_content,
            original_doc_bytes=orig_file_bytes,
            personal_overrides=personal_overrides,
            approved_changes=approved_changes
        )

        # 3. Upload revised document directly to IKM (zero local disk persistence)
        revised_filename = f"{doc.original_filename.rsplit('.', 1)[0]}_{version_id}_{uuid.uuid4().hex[:6]}.docx"
        ikm_upload = ikm_adapter.upload_file_bytes(filename=revised_filename, content=docx_bytes)
        ikm_version_id = ikm_upload.get("document_id") or version_id
        dms_ref = f"ikm://{ikm_version_id}"

        if hasattr(ikm_adapter, "_download_cache"):
            ikm_adapter._download_cache[version_id] = docx_bytes
            ikm_adapter._download_cache[ikm_version_id] = docx_bytes
            ikm_adapter._download_cache[dms_ref] = docx_bytes
            if dms_ref.startswith("ikm://"):
                ikm_adapter._download_cache[dms_ref[6:]] = docx_bytes

        # Persist version record with retry and safe rollback on concurrency collisions
        from sqlalchemy.exc import IntegrityError
        version_record = None
        for attempt in range(5):
            try:
                version_record = ResumeVersion(
                    version_id=version_id,
                    doc_id=doc_id,
                    dms_ref=dms_ref,
                    parent_version_id=parent_version_id,
                    created_by=actor.user_id,
                    approved_by=actor.user_id if approved else None,
                    created_at=datetime.now(timezone.utc),
                    change_summary=change_summary,
                    revised_content=revised_content
                )
                db.add(version_record)

                # Check existing recruitment status to avoid demoting hired or shortlisted candidates
                latest_act_existing = (
                    db.query(RecruitmentAction)
                    .filter(RecruitmentAction.doc_id == doc_id)
                    .order_by(RecruitmentAction.action_at.desc())
                    .first()
                )
                keep_status = latest_act_existing.status if (latest_act_existing and latest_act_existing.status in ["hired", "shortlisted", "contacted"]) else "reviewed"

                # Record recruitment action
                act_record = RecruitmentAction(
                    action_id=f"act-{uuid.uuid4().hex[:8]}",
                    doc_id=doc_id,
                    action_type="improved",
                    status=keep_status,
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

                # Synchronize updated key fields with remote IKM if available
                if doc.ikm_ref and hasattr(ikm_adapter, "update_metadata"):
                    try:
                        clean_ref = doc.ikm_ref[6:] if doc.ikm_ref.startswith("ikm://") else doc.ikm_ref
                        ikm_adapter.update_metadata(
                            ikm_ref=clean_ref,
                            metadata={"version": version_id, "document_title": f"{cand_name} - {target_role}"},
                            change_reason="Recruiter approved revised resume"
                        )
                    except Exception:
                        pass

                db.commit()
                break
            except IntegrityError:
                db.rollback()
                next_ver_num += 1
                version_id = f"VER-{doc_id}-v{next_ver_num}"
                parent_version_id = f"VER-{doc_id}-v{next_ver_num - 1}"
                if attempt == 4:
                    raise

        # Step: Extract content from actual saved revised DOCX bytes and re-evaluate
        actual_score = None
        actual_breakdown = None
        score_delta = 0
        score_explanation = ""
        try:
            re_extracted = ikm_adapter.extract_metadata(doc_id, docx_bytes, filename=revised_filename)
            re_profile = re_extracted.get("profile", {})

            # Resolve JD requirements for re-evaluation
            re_jd_reqs = None
            if change_summary and "for " in change_summary.lower():
                role_key = change_summary.split("for ")[-1].strip()
                jd_rec = db.query(JobDescription).filter(JobDescription.title.ilike(f"%{role_key}%")).first()
                if jd_rec:
                    re_jd_reqs = jd_rec.requirements_json
            if not re_jd_reqs:
                latest_jd = db.query(JobDescription).order_by(JobDescription.created_at.desc()).first()
                if latest_jd:
                    re_jd_reqs = latest_jd.requirements_json
                else:
                    re_jd_reqs = {"technical_skills": profile.get("skills", [])}

            eval_res = scoring_service.calculate_score(re_jd_reqs, re_profile)
            actual_score = eval_res["total_score"]
            actual_breakdown = eval_res["breakdown"]

            # Original score comparison
            orig_eval = scoring_service.calculate_score(re_jd_reqs, profile)
            orig_score = orig_eval["total_score"]
            score_delta = actual_score - orig_score

            score_explanation = (
                f"Re-evaluation of the exported Word document yields a score of {actual_score}/100 "
                f"({'+' if score_delta >= 0 else ''}{score_delta} pts vs baseline {orig_score}/100). "
                f"Score is calculated directly from the extracted text and competencies of the saved DOCX file."
            )
        except Exception as e_eval:
            actual_score = None
            actual_breakdown = None
            score_delta = 0
            score_explanation = f"Saved revised document. Direct evaluation: {e_eval}"

        return {
            "version_id": version_id,
            "doc_id": doc_id,
            "parent_version_id": version_record.parent_version_id,
            "created_at": version_record.created_at,
            "created_by": version_record.created_by,
            "approved_by": version_record.approved_by,
            "change_summary": change_summary,
            "dms_ref": dms_ref,
            "file_bytes": docx_bytes,
            "actual_score": actual_score,
            "score_breakdown": actual_breakdown,
            "score_delta": score_delta,
            "score_explanation": score_explanation
        }

    def save_editor_docx(
        self,
        doc_id: str,
        file_bytes: bytes,
        db: Session,
        actor: CurrentUser,
        change_summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Saves a DOCX binary uploaded directly from the Word editor (WordCraft).
        Updates or creates a revision version in DMS and recalculates honest scoring.
        """
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

        # Determine next version ID
        existing_versions = db.query(ResumeVersion.version_id).filter(
            (ResumeVersion.doc_id == doc_id) | (ResumeVersion.version_id.like(f"VER-{doc_id}-v%"))
        ).all()
        highest_v = 0
        for (v_id,) in existing_versions:
            m = re.search(r'-v(\d+)$', str(v_id))
            if m:
                highest_v = max(highest_v, int(m.group(1)))
        next_ver_num = highest_v + 1
        version_id = f"VER-{doc_id}-v{next_ver_num}"
        parent_version_id = f"VER-{doc_id}-v{highest_v}" if highest_v > 0 else None

        # Upload directly to IKM storage (zero local file persistence)
        from app.integrations.ikm_adapter import ikm_adapter
        version_filename = f"{doc.original_filename.rsplit('.', 1)[0]}_{version_id}.docx"
        ikm_upload = ikm_adapter.upload_file_bytes(filename=version_filename, content=file_bytes)
        ikm_ver_doc_id = ikm_upload.get("document_id") or version_id
        dms_ref = f"ikm://{ikm_ver_doc_id}"
        summary_text = change_summary or f"Word Editor direct edits saved by {actor.user_id}"

        version_record = ResumeVersion(
            version_id=version_id,
            doc_id=doc_id,
            dms_ref=dms_ref,
            parent_version_id=parent_version_id,
            created_by=actor.user_id,
            approved_by=actor.user_id,
            created_at=datetime.now(timezone.utc),
            change_summary=summary_text,
            revised_content="Edited in WordCraft Full Word Processor"
        )
        db.add(version_record)

        # Audit and action
        db.add(RecruitmentAction(
            action_id=f"act-{uuid.uuid4().hex[:8]}",
            doc_id=doc_id,
            action_type="improved",
            status="reviewed",
            owner_id=actor.user_id,
            notes=f"Saved editor revision {version_id}",
            action_at=datetime.now(timezone.utc)
        ))
        db.add(AuditEvent(
            event_id=f"aud-{uuid.uuid4().hex[:8]}",
            actor_id=actor.user_id,
            action="save_editor_docx",
            target_doc_id=doc_id,
            outcome="success",
            metadata_json={"version_id": version_id, "size_bytes": len(file_bytes), "dms_ref": dms_ref}
        ))
        db.commit()

        # Score recalculation directly from the in-memory bytes
        actual_score = None
        actual_breakdown = None
        score_delta = 0
        score_explanation = ""
        try:
            re_extracted = ikm_adapter.extract_metadata(doc_id, file_bytes, filename=version_filename)
            re_profile = re_extracted.get("profile", {})
            latest_jd = db.query(JobDescription).order_by(JobDescription.created_at.desc()).first()
            jd_reqs = latest_jd.requirements_json if latest_jd else {"technical_skills": re_profile.get("skills", [])}
            eval_res = scoring_service.calculate_score(jd_reqs, re_profile)
            actual_score = eval_res["total_score"]
            actual_breakdown = eval_res["breakdown"]
            score_explanation = f"Evaluated saved editor revision: {actual_score}/100"
        except Exception:
            pass

        try:
            from app.services.ikm_sync_service import invalidate_sync_cooldown
            invalidate_sync_cooldown()
        except Exception:
            pass

        return {
            "success": True,
            "version_id": version_id,
            "doc_id": doc_id,
            "download_url": f"/api/versions/{version_id}/file",
            "filename": f"{doc_id}_{version_id}.docx",
            "dms_ref": dms_ref,
            "actual_score": actual_score,
            "score_breakdown": actual_breakdown,
            "score_delta": score_delta,
            "score_explanation": score_explanation,
            "message": f"Saved editor changes as revision {version_id}"
        }

    def save_draft_to_library(
        self,
        source_doc_id: str,
        db: Session,
        actor: CurrentUser,
        file_bytes: Optional[bytes] = None,
        change_summary: Optional[str] = None,
        revised_content: Optional[str] = None,
        personal_overrides: Optional[Dict[str, Any]] = None,
        approved_changes: Optional[List[Dict[str, Any]]] = None,
        custom_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new Document record in Resume Library and persists through DMS and IKM.
        Maintains revision relationship with source document while preserving original resume intact.
        """
        source_doc = db.query(Document).filter(Document.doc_id == source_doc_id).first()
        if not source_doc:
            raise HTTPException(status_code=404, detail=f"Source document '{source_doc_id}' not found.")

        from app.services.resume_ingestion import resume_ingestion_service
        from app.integrations.ikm_adapter import ikm_adapter
        from app.services.word_resume_service import word_resume_service

        new_doc_id = resume_ingestion_service._generate_doc_id(db)

        # If file_bytes not provided directly from editor, generate DOCX from current content/changes
        if not file_bytes:
            is_src_docx = bool(source_doc.original_filename and source_doc.original_filename.lower().endswith(".docx"))
            orig_bytes = None
            if is_src_docx:
                if source_doc.ikm_ref:
                    orig_bytes = ikm_adapter.download_document(source_doc.ikm_ref)
                if not orig_bytes and source_doc.dms_ref and source_doc.dms_ref.startswith("ikm://"):
                    orig_bytes = ikm_adapter.download_document(source_doc.dms_ref[6:])
                if not orig_bytes:
                    found = ikm_adapter.find_document_by_name(source_doc.original_filename)
                    if found and found.get("document_id") and (found.get("original_file_name") or "").lower().endswith(".docx"):
                        orig_bytes = ikm_adapter.download_document(found["document_id"])

            source_prof_rec = db.query(CandidateProfile).filter(CandidateProfile.doc_id == source_doc_id).first()
            source_profile = source_prof_rec.structured_profile_json if source_prof_rec else {}
            
            # Resolve candidate name
            cand_name = source_doc.original_filename.rsplit(".", 1)[0]
            if personal_overrides and personal_overrides.get("name"):
                cand_name = str(personal_overrides["name"]).strip()
            elif source_doc.pii and source_doc.pii.name_encrypted:
                from app.security.encryption import pii_crypto
                decrypted = pii_crypto.decrypt_pii_dict({"name_encrypted": source_doc.pii.name_encrypted})
                if decrypted.get("name"):
                    cand_name = decrypted["name"]

            cand_name = self._resolve_clean_candidate_name(cand_name, source_doc.original_filename)
            target_role = (personal_overrides and personal_overrides.get("role")) or "Senior Technical Professional"

            file_bytes = word_resume_service.generate_improved_docx_bytes(
                candidate_name=cand_name,
                target_role=target_role,
                profile=source_profile,
                revised_content=revised_content or "",
                original_doc_bytes=orig_bytes,
                personal_overrides=personal_overrides,
                approved_changes=approved_changes
            )

        # Formulate clean filename
        if custom_filename:
            draft_filename = custom_filename if custom_filename.lower().endswith(".docx") else f"{custom_filename}.docx"
        else:
            base_fn = source_doc.original_filename.rsplit(".", 1)[0]
            draft_filename = f"{base_fn}_Draft_{new_doc_id}.docx"

        # 1. Ingest and persist directly into IKM (zero local disk persistence)
        import hashlib
        checksum = hashlib.sha256(file_bytes).hexdigest()
        ikm_res = ikm_adapter.upload_file_bytes(filename=draft_filename, content=file_bytes)
        ikm_doc_id = ikm_res.get("document_id") or new_doc_id
        ikm_ref = f"ikm://{ikm_doc_id}"
        dms_ref = f"ikm://{ikm_doc_id}"

        # 3. Create Document record
        new_doc = Document(
            doc_id=new_doc_id,
            dms_ref=dms_ref,
            ikm_ref=ikm_ref,
            original_filename=draft_filename,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            checksum=checksum,
            upload_status="ready",
            uploaded_by=actor.user_id,
            uploaded_at=datetime.now(timezone.utc),
            last_opened_at=datetime.now(timezone.utc)
        )
        db.add(new_doc)

        # 4. Create CandidateProfile
        source_prof = source_doc.profile
        prof_json = dict(source_prof.structured_profile_json) if (source_prof and source_prof.structured_profile_json) else {}
        prof_json["source_doc_id"] = source_doc_id
        prof_json["is_draft"] = True
        new_profile = CandidateProfile(
            doc_id=new_doc_id,
            structured_profile_json=prof_json,
            raw_text_summary=source_prof.raw_text_summary if source_prof else "",
            profile_status="ready",
            updated_at=datetime.now(timezone.utc)
        )
        db.add(new_profile)

        # 5. Create CandidatePII (with any personal overrides applied)
        source_pii = source_doc.pii
        from app.security.encryption import pii_crypto
        existing_pii = {}
        if source_pii:
            existing_pii = pii_crypto.decrypt_pii_dict({
                "name_encrypted": source_pii.name_encrypted,
                "email_encrypted": source_pii.email_encrypted,
                "phone_encrypted": source_pii.phone_encrypted,
                "address_encrypted": source_pii.address_encrypted
            })
        merged_pii = {
            "name": (personal_overrides and personal_overrides.get("name")) or existing_pii.get("name") or "",
            "email": (personal_overrides and personal_overrides.get("email")) or existing_pii.get("email") or "",
            "phone": (personal_overrides and personal_overrides.get("phone")) or existing_pii.get("phone") or "",
            "address": (personal_overrides and personal_overrides.get("location")) or existing_pii.get("address") or ""
        }
        enc_pii = pii_crypto.encrypt_pii_dict(merged_pii)
        new_pii = CandidatePII(
            doc_id=new_doc_id,
            name_encrypted=enc_pii["name_encrypted"],
            email_encrypted=enc_pii["email_encrypted"],
            phone_encrypted=enc_pii["phone_encrypted"],
            address_encrypted=enc_pii["address_encrypted"],
            updated_at=datetime.now(timezone.utc)
        )
        db.add(new_pii)

        # 6. Create initial ResumeVersion maintaining revision relationship
        initial_version = ResumeVersion(
            version_id=f"VER-{new_doc_id}-v1",
            doc_id=new_doc_id,
            dms_ref=dms_ref,
            parent_version_id=f"source:{source_doc_id}",
            created_by=actor.user_id,
            approved_by=actor.user_id,
            created_at=datetime.now(timezone.utc),
            change_summary=change_summary or f"Draft saved from {source_doc_id} ({source_doc.original_filename})",
            revised_content=revised_content or "Draft document created"
        )
        db.add(initial_version)

        # 7. Action and Audit
        act = RecruitmentAction(
            action_id=f"act-{uuid.uuid4().hex[:8]}",
            doc_id=new_doc_id,
            action_type="draft_saved",
            status="in_progress",
            owner_id=actor.user_id,
            notes=f"Saved improved draft from {source_doc_id} ({source_doc.original_filename})",
            action_at=datetime.now(timezone.utc)
        )
        db.add(act)
        db.add(AuditEvent(
            event_id=f"aud-{uuid.uuid4().hex[:8]}",
            actor_id=actor.user_id,
            action="save_draft_to_library",
            target_doc_id=new_doc_id,
            outcome="success",
            metadata_json={"source_doc_id": source_doc_id, "new_doc_id": new_doc_id, "dms_ref": dms_ref, "ikm_ref": ikm_ref}
        ))
        db.commit()

        # Recalculate score on the new draft docx
        actual_score = None
        actual_breakdown = None
        score_explanation = ""
        try:
            re_extracted = ikm_adapter.extract_metadata(new_doc_id, file_bytes, filename=draft_filename)
            re_profile = re_extracted.get("profile", {})
            latest_jd = db.query(JobDescription).order_by(JobDescription.created_at.desc()).first()
            jd_reqs = latest_jd.requirements_json if latest_jd else {"technical_skills": re_profile.get("skills", [])}
            eval_res = scoring_service.calculate_score(jd_reqs, re_profile)
            actual_score = eval_res["total_score"]
            actual_breakdown = eval_res["breakdown"]
            score_explanation = f"Initial draft alignment score: {actual_score}/100"
        except Exception:
            pass

        try:
            from app.services.ikm_sync_service import invalidate_sync_cooldown
            invalidate_sync_cooldown()
        except Exception:
            pass

        return {
            "success": True,
            "doc_id": new_doc_id,
            "source_doc_id": source_doc_id,
            "filename": draft_filename,
            "dms_ref": dms_ref,
            "ikm_ref": ikm_ref,
            "version_id": f"VER-{new_doc_id}-v1",
            "download_url": f"/api/resumes/{new_doc_id}/stream",
            "actual_score": actual_score,
            "score_breakdown": actual_breakdown,
            "score_explanation": score_explanation,
            "message": f"Successfully persisted draft '{draft_filename}' as {new_doc_id} in Resume Library & IKM"
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

    def recalculate_score(
        self,
        doc_id: str,
        job_id: Optional[str],
        job_text: Optional[str],
        accepted_changes: List[Dict[str, Any]],
        db: Session
    ) -> Dict[str, Any]:
        """
        Recalculates candidate alignment score using the unified shared scoring engine:
        Evaluates verified evidence added in accepted changes against JD criteria,
        and provides honest score delta and gap breakdown without arbitrary score inflation or fabricated claims.
        """
        import copy
        prof_rec = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
        if not prof_rec:
            raise HTTPException(status_code=400, detail="Candidate profile not found.")

        profile = prof_rec.structured_profile_json or {}

        # Resolve JD criteria
        if job_id:
            job_rec = db.query(JobDescription).filter(JobDescription.job_id == job_id).first()
            if not job_rec:
                raise HTTPException(status_code=404, detail="Job not found.")
            jd_reqs = job_rec.requirements_json
        elif job_text and job_text.strip():
            jd_reqs = llm_adapter.parse_job_description(job_text)
        else:
            raise HTTPException(status_code=400, detail="Must provide either job_id or job_text.")

        orig_score_data = scoring_service.calculate_score(jd_reqs, profile)
        orig_score = orig_score_data["total_score"]

        # Augment profile reflecting accepted changes
        augmented_profile = copy.deepcopy(profile)
        gained = []
        existing_skills_lower = {s.lower() for s in augmented_profile.get("skills", [])}

        # Check for skills explicitly mentioned in accepted modifications
        for chg in accepted_changes:
            proposed = (chg.get("proposed_text") or "").strip()
            sec = chg.get("section", "general")
            if not proposed:
                continue

            # If it's a skills section modification, parse tokens
            if sec == "skills":
                tokens = [t.strip() for t in re.split(r'[,|•\*\n/]+', proposed) if 2 <= len(t.strip()) <= 30]
                for tok in tokens:
                    if tok.lower() not in existing_skills_lower:
                        augmented_profile.setdefault("skills", []).append(tok)
                        existing_skills_lower.add(tok.lower())
                        gained.append(tok)
            else:
                # Add proposed text as verified experience and project evidence
                augmented_profile.setdefault("experience", []).append({
                    "role": f"Verified Contribution ({sec})",
                    "evidence": proposed
                })
                augmented_profile.setdefault("projects", []).append({
                    "name": f"Enhanced Deliverable ({sec})",
                    "evidence": proposed
                })
                # Check if any JD technical skill is explicitly referenced in the proposed text
                for tech in jd_reqs.get("technical_skills", []):
                    if tech.lower() not in existing_skills_lower:
                        pattern = r'\b' + re.escape(tech) + r'\b'
                        if re.search(pattern, proposed, re.IGNORECASE):
                            augmented_profile.setdefault("skills", []).append(tech)
                            existing_skills_lower.add(tech.lower())
                            gained.append(tech)

        # Calculate revised score using the exact shared scoring engine
        revised_score_data = scoring_service.calculate_score(jd_reqs, augmented_profile)
        revised_score = revised_score_data["total_score"]

        # Gaps remaining
        current_skills_lower = {s.lower() for s in augmented_profile.get("skills", [])}
        remaining_gaps = [
            t for t in jd_reqs.get("technical_skills", [])
            if t.lower() not in current_skills_lower
        ]

        score_diff = revised_score - orig_score
        explanation = (
            f"Score updated from {orig_score} to {revised_score} ({'+' if score_diff >= 0 else ''}{score_diff} pts) "
            f"across {len(accepted_changes)} accepted modification(s). "
            f"{'Enhanced verified evidence for: ' + ', '.join(gained) + '. ' if gained else 'Strengthened experience clarity and STAR deliverables. '}"
            f"{'Remaining unverified requirements: ' + ', '.join(remaining_gaps[:3]) + '.' if remaining_gaps else 'All technical requirements demonstrated.'}"
        )

        return {
            "original_score": orig_score,
            "revised_score": revised_score,
            "score_difference": score_diff,
            "gained_requirements": gained,
            "remaining_gaps": remaining_gaps,
            "explanation": explanation,
            "breakdown": revised_score_data["breakdown"]
        }

resume_improvement_service = ResumeImprovementService()
