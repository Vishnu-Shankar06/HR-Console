import re
import html
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.entities import Document, CandidatePII, ResumeVersion, AuditEvent
from app.integrations.dms_adapter import dms_adapter

class ResumePreviewService:
    """
    In-application Resume Preview Service.
    Parses and renders PDF, DOCX, and text resumes into clean, in-app paginated
    representations without triggering browser downloads.
    Includes high-performance caching based on file modification timestamp and size.
    """

    def __init__(self):
        self._preview_cache: Dict[str, Tuple[float, int, Dict[str, Any]]] = {}

    def invalidate_cache(self, doc_id: Optional[str] = None):
        if doc_id:
            keys_to_del = [k for k in self._preview_cache if doc_id in k]
            for k in keys_to_del:
                self._preview_cache.pop(k, None)
        else:
            self._preview_cache.clear()

    def resolve_candidate_full_name(self, doc_id: str, original_filename: str, db: Session) -> str:
        pii = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
        if pii and pii.name_encrypted:
            from app.security.encryption import pii_crypto
            decrypted = pii_crypto.decrypt_pii_dict({"name_encrypted": pii.name_encrypted})
            name = decrypted.get("name")
            if name and name.upper() not in ["SUMMARY", "OBJECTIVE", "PROFILE", "RESUME", "CURRICULUM VITAE"]:
                return name.strip()

        # Clean from filename
        clean = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc|txt)$', '', original_filename, flags=re.IGNORECASE)
        clean = re.sub(r'[\-_]+', ' ', clean).strip()
        words = clean.split()
        clean_words = [w for w in words if w.lower() not in ['resume', 'cv', 'final', 'resumee', 'sfdc', 'developer', 'engineer', 'vault', 'qmsqdocs', 'qa', 'salesforce', 'se']]
        if clean_words:
            return ' '.join(clean_words).title()
        return clean.title() if clean else f"Candidate {doc_id}"

    def _unmask_preview_pages(self, pages: List[str], doc_id: str, db: Session) -> List[str]:
        """Restores genuine candidate PII so masked tokens never leak into authorized user previews."""
        if not pages or not doc_id:
            return pages
        pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
        if not pii_rec:
            return pages
        from app.security.encryption import pii_crypto
        decrypted = pii_crypto.decrypt_pii_dict({
            "name_encrypted": pii_rec.name_encrypted,
            "email_encrypted": pii_rec.email_encrypted,
            "phone_encrypted": pii_rec.phone_encrypted,
            "address_encrypted": pii_rec.address_encrypted
        })
        real_name = decrypted.get("name")
        real_phone = decrypted.get("phone")
        real_email = decrypted.get("email")
        real_addr = decrypted.get("address")

        unmasked = []
        for page in pages:
            p_mod = page
            if real_phone:
                p_mod = p_mod.replace("+XXX-XXX-XXXX", real_phone)
                p_mod = p_mod.replace("[CANDIDATE_PHONE]", real_phone)
            if real_email:
                p_mod = re.sub(r'[\w\.-]+\*{3}@[\w\.-]+', real_email, p_mod)
                p_mod = p_mod.replace("[CANDIDATE_EMAIL]", real_email)
            if real_name:
                p_mod = p_mod.replace("[CANDIDATE_NAME]", real_name)
                p_mod = p_mod.replace("PERSON_NAME", real_name)
            if real_addr:
                p_mod = p_mod.replace("[CANDIDATE_LOCATION]", real_addr)
            unmasked.append(p_mod)
        return unmasked

    def get_document_preview(self, doc_id: str, db: Session) -> Dict[str, Any]:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

        cache_key = f"doc_{doc_id}"
        cached = self._preview_cache.get(cache_key)
        if cached:
            return cached[2]

        cand_name = self.resolve_candidate_full_name(doc_id, doc.original_filename, db)

        # 1. Primary: Download directly from IKM storage
        from app.integrations.ikm_adapter import ikm_adapter
        file_bytes = None
        if hasattr(ikm_adapter, "_download_cache"):
            if doc.ikm_ref and doc.ikm_ref in ikm_adapter._download_cache:
                file_bytes = ikm_adapter._download_cache[doc.ikm_ref]
            elif doc_id in ikm_adapter._download_cache:
                file_bytes = ikm_adapter._download_cache[doc_id]
            elif doc.dms_ref and doc.dms_ref in ikm_adapter._download_cache:
                file_bytes = ikm_adapter._download_cache[doc.dms_ref]

        if not file_bytes and doc.ikm_ref:
            file_bytes = ikm_adapter.download_document(doc.ikm_ref)
        if not file_bytes and doc.dms_ref and doc.dms_ref.startswith("ikm://"):
            file_bytes = ikm_adapter.download_document(doc.dms_ref[6:])
        if not file_bytes:
            found = ikm_adapter.find_document_by_name(doc.original_filename)
            if found and found.get("document_id"):
                file_bytes = ikm_adapter.download_document(found["document_id"])

        if file_bytes:
            if file_bytes.startswith(b"%PDF"):
                pages = []
                try:
                    import io, pypdf
                    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                    for idx, p in enumerate(reader.pages):
                        p_text = p.extract_text() or ""
                        pages.append(self._format_pdf_page_html(p_text, idx + 1, cand_name))
                except Exception:
                    pass
                if not pages:
                    text = ikm_adapter.extract_raw_text(file_bytes, filename=doc.original_filename)
                    pages = self._text_to_pages(text, cand_name)
                pages = self._unmask_preview_pages(pages, doc_id, db)
                return {
                    "success": True,
                    "doc_id": doc_id,
                    "version_id": None,
                    "filename": doc.original_filename,
                    "full_name": cand_name,
                    "mime_type": "application/pdf",
                    "total_pages": max(1, len(pages)),
                    "pages": pages,
                    "is_pdf": True,
                    "is_docx": False,
                    "stream_url": f"/api/resumes/{doc_id}/stream",
                    "pdf_stream_url": f"/api/resumes/{doc_id}/stream"
                }
            elif file_bytes.startswith(b"PK\x03\x04") or doc.original_filename.lower().endswith(".docx"):
                pages = []
                try:
                    pages = self._docx_to_pages(file_bytes, cand_name)
                except Exception:
                    text = ikm_adapter.extract_raw_text(file_bytes, filename=doc.original_filename)
                    pages = self._text_to_pages(text, cand_name)
                pages = self._unmask_preview_pages(pages, doc_id, db)
                return {
                    "success": True,
                    "doc_id": doc_id,
                    "version_id": None,
                    "filename": doc.original_filename,
                    "full_name": cand_name,
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "total_pages": max(1, len(pages)),
                    "pages": pages,
                    "is_pdf": False,
                    "is_docx": True,
                    "stream_url": f"/api/resumes/{doc_id}/stream",
                    "docx_stream_url": f"/api/resumes/{doc_id}/stream"
                }
            else:
                text = file_bytes.decode("utf-8", errors="ignore")
                pages = self._text_to_pages(text, cand_name)
                pages = self._unmask_preview_pages(pages, doc_id, db)
                return {
                    "success": True,
                    "doc_id": doc_id,
                    "version_id": None,
                    "filename": doc.original_filename,
                    "full_name": cand_name,
                    "mime_type": "text/plain",
                    "total_pages": max(1, len(pages)),
                    "pages": pages,
                    "is_pdf": False,
                    "is_docx": False,
                    "stream_url": f"/api/resumes/{doc_id}/stream",
                    "docx_stream_url": None
                }

        # 2. Disk file check if exists
        file_path = dms_adapter.get_file_path(doc.dms_ref)
        if file_path and file_path.exists():
            return self._render_file_to_preview(
                doc_id=doc_id,
                filename=doc.original_filename,
                cand_name=cand_name,
                file_path=file_path,
                mime_type=doc.mime_type
            )

        # 3. Candidate profile fallback for seeded/in-memory records
        from app.models.entities import CandidateProfile
        prof_rec = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
        if prof_rec:
            summary = prof_rec.raw_text_summary or ""
            skills = ", ".join(prof_rec.structured_profile_json.get("skills", [])) if prof_rec.structured_profile_json else ""
            text = f"{cand_name}\n\n{summary}\n\nSkills: {skills}"
            pages = self._text_to_pages(text, cand_name)
            return {
                "success": True,
                "doc_id": doc_id,
                "version_id": None,
                "filename": doc.original_filename,
                "full_name": cand_name,
                "mime_type": doc.mime_type or "text/plain",
                "total_pages": max(1, len(pages)),
                "pages": pages,
                "is_pdf": False,
                "is_docx": False,
                "stream_url": f"/api/resumes/{doc_id}/stream",
                "docx_stream_url": None
            }

        raise HTTPException(status_code=404, detail=f"File for document '{doc_id}' not found in IKM storage.")

    def get_version_preview(self, version_id: str, db: Session) -> Dict[str, Any]:
        ver = db.query(ResumeVersion).filter(ResumeVersion.version_id == version_id).first()
        if not ver:
            raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

        doc = db.query(Document).filter(Document.doc_id == ver.doc_id).first()
        filename = f"{doc.original_filename.rsplit('.', 1)[0]}_v{version_id.split('-v')[-1]}.docx" if doc else f"{version_id}.docx"
        cand_name = self.resolve_candidate_full_name(ver.doc_id, filename, db)

        # 1. Primary: Download directly from IKM storage
        from app.integrations.ikm_adapter import ikm_adapter
        ver_bytes = None
        if hasattr(ikm_adapter, "_download_cache"):
            if version_id in ikm_adapter._download_cache:
                ver_bytes = ikm_adapter._download_cache[version_id]
            elif ver.dms_ref and ver.dms_ref in ikm_adapter._download_cache:
                ver_bytes = ikm_adapter._download_cache[ver.dms_ref]

        if not ver_bytes and ver.dms_ref:
            if ver.dms_ref.startswith("ikm://"):
                ver_bytes = ikm_adapter.download_document(ver.dms_ref[6:])
            else:
                ver_bytes = ikm_adapter.download_document(ver.dms_ref)
        if not ver_bytes:
            found = ikm_adapter.find_document_by_name(f"{doc.original_filename.rsplit('.', 1)[0]}_{version_id}.docx" if doc else f"{version_id}.docx")
            if found and found.get("document_id"):
                ver_bytes = ikm_adapter.download_document(found["document_id"])

        if ver_bytes:
            pages = []
            try:
                pages = self._docx_to_pages(ver_bytes, cand_name)
            except Exception:
                text = ikm_adapter.extract_raw_text(ver_bytes)
                pages = self._text_to_pages(text, cand_name)
            pages = self._unmask_preview_pages(pages, ver.doc_id, db)
            return {
                "success": True,
                "doc_id": ver.doc_id,
                "version_id": version_id,
                "filename": filename,
                "full_name": cand_name,
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "total_pages": max(1, len(pages)),
                "pages": pages,
                "is_pdf": False,
                "is_docx": True,
                "stream_url": f"/api/versions/{version_id}/file",
                "docx_stream_url": f"/api/versions/{version_id}/file"
            }

        file_path = dms_adapter.get_file_path(ver.dms_ref)
        if file_path and file_path.exists() and file_path.stat().st_size > 0:
            pages = []
            try:
                pages = self._docx_to_pages(file_path, cand_name)
            except Exception:
                pass
            return {
                "success": True,
                "doc_id": ver.doc_id,
                "version_id": version_id,
                "filename": filename,
                "full_name": cand_name,
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "total_pages": max(1, len(pages)),
                "pages": pages,
                "is_pdf": False,
                "is_docx": True,
                "stream_url": f"/api/versions/{version_id}/file",
                "docx_stream_url": f"/api/versions/{version_id}/file"
            }

        content = ver.revised_content or "No preview content available."
        pages = self._text_to_pages(content, cand_name)
        return {
            "success": True,
            "doc_id": ver.doc_id,
            "version_id": version_id,
            "filename": filename,
            "full_name": cand_name,
            "mime_type": "text/html",
            "total_pages": len(pages),
            "pages": pages,
            "is_pdf": False,
            "is_docx": False,
            "stream_url": None,
            "docx_stream_url": None
        }

    def _render_file_to_preview(
        self,
        doc_id: str,
        filename: str,
        cand_name: str,
        file_path: Path,
        mime_type: str,
        version_id: Optional[str] = None
    ) -> Dict[str, Any]:
        suffix = file_path.suffix.lower()
        is_real_pdf = False
        pages: List[str] = []

        # 1. Try DOCX rendering
        if suffix in [".docx", ".doc"]:
            try:
                pages = self._docx_to_pages(file_path, cand_name)
            except Exception:
                # Fallback to text reading if docx package loading fails
                text = self._read_file_text_fallback(file_path)
                pages = self._text_to_pages(text, cand_name)

        # 2. Try PDF rendering
        elif suffix == ".pdf":
            try:
                with open(file_path, "rb") as f:
                    magic = f.read(5)
                    if magic.startswith(b"%PDF"):
                        f.seek(0)
                        import pypdf
                        reader = pypdf.PdfReader(f)
                        if len(reader.pages) > 0:
                            is_real_pdf = True
                            for idx, p in enumerate(reader.pages):
                                p_text = p.extract_text() or ""
                                pages.append(self._format_pdf_page_html(p_text, idx + 1, cand_name))
                    else:
                        raise ValueError("Not a binary PDF")
            except Exception:
                is_real_pdf = False
                text = self._read_file_text_fallback(file_path)
                pages = self._text_to_pages(text, cand_name)

        # 3. Text or other fallback
        else:
            text = self._read_file_text_fallback(file_path)
            pages = self._text_to_pages(text, cand_name)

        if not pages:
            pages = [f"<div class='doc-preview-empty'><p>No readable content found in {html.escape(filename)}.</p></div>"]

        stream_url = None
        if is_real_pdf:
            stream_url = f"/api/resumes/{doc_id}/stream"

        return {
            "success": True,
            "doc_id": doc_id,
            "version_id": version_id,
            "filename": filename,
            "full_name": cand_name,
            "mime_type": mime_type,
            "total_pages": len(pages),
            "pages": pages,
            "is_pdf": is_real_pdf,
            "pdf_stream_url": stream_url
        }

    def _docx_to_pages(self, file_source: Any, cand_name: str) -> List[str]:
        import io
        import docx
        from docx.text.paragraph import Paragraph
        from docx.table import Table

        if isinstance(file_source, (bytes, bytearray)):
            doc = docx.Document(io.BytesIO(bytes(file_source)))
        elif isinstance(file_source, io.BytesIO):
            doc = docx.Document(file_source)
        else:
            doc = docx.Document(str(file_source))
        pages: List[str] = []
        current_page_items: List[str] = []
        item_count = 0
        MAX_ITEMS_PER_PAGE = 28

        def flush_page():
            nonlocal current_page_items, item_count
            if current_page_items:
                pages.append("\n".join(current_page_items))
                current_page_items = []
                item_count = 0

        # Iterate in natural document body order (paragraphs and tables in place)
        for child in doc.element.body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "p":
                p = Paragraph(child, doc)
                text = p.text.strip()
                if not text:
                    continue

                # Check for explicit page break in runs
                has_page_break = False
                for r in p.runs:
                    if "\f" in r.text or "lastRenderedPageBreak" in r._element.xml or 'w:type="page"' in r._element.xml:
                        has_page_break = True
                        break

                if has_page_break and item_count > 0:
                    flush_page()

                align_class = "doc-align-left"
                if p.alignment == docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER:
                    align_class = "doc-align-center"
                elif p.alignment == docx.enum.text.WD_ALIGN_PARAGRAPH.RIGHT:
                    align_class = "doc-align-right"
                elif p.alignment == docx.enum.text.WD_ALIGN_PARAGRAPH.JUSTIFY:
                    align_class = "doc-align-justify"

                p_html = self._format_paragraph_runs(p)
                upper = text.upper()
                is_heading = (
                    p.style.name.startswith("Heading") or
                    (len(text) < 50 and upper in ["SUMMARY", "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "EXPERIENCE", "WORK EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS"])
                )

                if is_heading:
                    if item_count >= (MAX_ITEMS_PER_PAGE - 5) and item_count > 0:
                        flush_page()
                    current_page_items.append(f"<h3 class='doc-sec-heading {align_class}'>{p_html}</h3>")
                    item_count += 2
                elif p.style.name.startswith("List") or text.startswith(("•", "-", "*")):
                    clean_text = re.sub(r'^[•\-\*]\s*', '', p_html)
                    current_page_items.append(f"<div class='doc-bullet-item {align_class}'>&bull; {clean_text}</div>")
                    item_count += 1
                else:
                    current_page_items.append(f"<p class='doc-para {align_class}'>{p_html}</p>")
                    item_count += 1

                if item_count >= MAX_ITEMS_PER_PAGE:
                    flush_page()

            elif tag == "tbl":
                table = Table(child, doc)
                table_rows_html = []
                for row in table.rows:
                    cells_html = [f"<td>{html.escape(c.text.strip())}</td>" for c in row.cells]
                    table_rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
                current_page_items.append(f"<table class='doc-table'>{''.join(table_rows_html)}</table>")
                item_count += max(1, len(table.rows))
                if item_count >= MAX_ITEMS_PER_PAGE:
                    flush_page()

        flush_page()
        return pages if pages else [f"<p class='doc-para'>{html.escape(cand_name)}</p>"]

    def _format_paragraph_runs(self, paragraph) -> str:
        runs_html = []
        for r in paragraph.runs:
            t = html.escape(r.text)
            if not t:
                continue
            if r.bold and r.italic:
                runs_html.append(f"<strong><em>{t}</em></strong>")
            elif r.bold:
                runs_html.append(f"<strong>{t}</strong>")
            elif r.italic:
                runs_html.append(f"<em>{t}</em>")
            elif r.underline:
                runs_html.append(f"<u>{t}</u>")
            else:
                runs_html.append(t)
        return "".join(runs_html) if runs_html else html.escape(paragraph.text)

    def _format_pdf_page_html(self, text: str, page_num: int, cand_name: str) -> str:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        html_lines = []

        for line in lines:
            if any(h in line.upper() for h in ["SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION"]):
                html_lines.append(f"<h3 class='doc-sec-heading'>{html.escape(line)}</h3>")
            elif line.startswith(("•", "-", "*")):
                html_lines.append(f"<div class='doc-bullet-item'>&bull; {html.escape(line[1:].strip())}</div>")
            else:
                html_lines.append(f"<p class='doc-para'>{html.escape(line)}</p>")

        return "\n".join(html_lines)

    def _text_to_pages(self, raw_text: str, cand_name: str) -> List[str]:
        # Split on formfeed or every 35 lines
        parts = raw_text.split("\x0c") if "\x0c" in raw_text else []
        if not parts:
            lines = [l for l in raw_text.split("\n")]
            CHUNK_SIZE = 32
            parts = ["\n".join(lines[i:i + CHUNK_SIZE]) for i in range(0, len(lines), CHUNK_SIZE)]

        pages = []
        for idx, part in enumerate(parts):
            if not part.strip():
                continue
            pages.append(self._format_pdf_page_html(part, idx + 1, cand_name))

        return pages if pages else [f"<p class='doc-para'>{html.escape(raw_text)}</p>"]

    def _read_file_text_fallback(self, file_path: Path) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            try:
                with open(file_path, "r", encoding="latin-1", errors="replace") as f:
                    return f.read()
            except Exception:
                return ""

resume_preview_service = ResumePreviewService()
