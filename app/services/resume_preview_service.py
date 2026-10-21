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

    def get_document_preview(self, doc_id: str, db: Session) -> Dict[str, Any]:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

        cache_key = f"doc_{doc_id}"
        cached = self._preview_cache.get(cache_key)
        if cached:
            return cached[2]

        cand_name = self.resolve_candidate_full_name(doc_id, doc.original_filename, db)

        # 1. Primary: If registered in remote IKM, query actual rendered preview
        from app.integrations.ikm_adapter import ikm_adapter
        if doc.ikm_ref and not doc.ikm_ref.startswith("local-") and not doc.ikm_ref.startswith("ikm-"):
            prev_data = ikm_adapter.get_document_preview_data(doc.ikm_ref)
            if prev_data and prev_data.get("content_bytes_b64"):
                try:
                    import base64, io, pypdf
                    pdf_bytes = base64.b64decode(prev_data["content_bytes_b64"])
                    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
                    pages = []
                    for idx, p in enumerate(reader.pages):
                        p_text = p.extract_text() or ""
                        pages.append(self._format_pdf_page_html(p_text, idx + 1, cand_name))
                    if not pages:
                        pages = [f"<div class='doc-preview-empty'><p>Document content available in IKM.</p></div>"]
                    rendered = {
                        "success": True,
                        "doc_id": doc_id,
                        "version_id": None,
                        "filename": doc.original_filename,
                        "full_name": cand_name,
                        "mime_type": "application/pdf",
                        "total_pages": len(pages),
                        "pages": pages,
                        "is_pdf": True,
                        "pdf_stream_url": f"/api/resumes/{doc_id}/stream"
                    }
                    self._preview_cache[cache_key] = (0.0, len(pdf_bytes), rendered)
                    return rendered
                except Exception:
                    pass

        # 2. Local File or IKM download recovery
        file_path = dms_adapter.get_file_path(doc.dms_ref)
        if not file_path or not file_path.exists():
            # Attempt to pull original from IKM if local disk file is missing
            if doc.ikm_ref and not doc.ikm_ref.startswith("local-") and not doc.ikm_ref.startswith("ikm-"):
                downloaded = ikm_adapter.download_document(doc.ikm_ref)
                if downloaded:
                    try:
                        ext = doc.original_filename.rsplit(".", 1)[-1].lower() if "." in doc.original_filename else "docx"
                        target_path = dms_adapter.originals_dir / f"{doc.doc_id}.{ext}"
                        with open(target_path, "wb") as f:
                            f.write(downloaded)
                        file_path = target_path
                    except Exception:
                        pass

        if not file_path or not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File for document '{doc_id}' not found in IKM or storage.")

        rendered = self._render_file_to_preview(
            doc_id=doc_id,
            filename=doc.original_filename,
            cand_name=cand_name,
            file_path=file_path,
            mime_type=doc.mime_type
        )
        try:
            stat = file_path.stat()
            self._preview_cache[cache_key] = (stat.st_mtime, stat.st_size, rendered)
        except Exception:
            self._preview_cache[cache_key] = (0.0, 0, rendered)
        return rendered

    def get_version_preview(self, version_id: str, db: Session) -> Dict[str, Any]:
        ver = db.query(ResumeVersion).filter(ResumeVersion.version_id == version_id).first()
        if not ver:
            raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

        file_path = dms_adapter.get_file_path(ver.dms_ref)
        doc = db.query(Document).filter(Document.doc_id == ver.doc_id).first()
        filename = f"{doc.original_filename.rsplit('.', 1)[0]}_v{version_id.split('-v')[-1]}.docx" if doc else f"{version_id}.docx"
        cand_name = self.resolve_candidate_full_name(ver.doc_id, filename, db)

        cache_key = f"ver_{version_id}"
        if file_path and file_path.exists():
            try:
                stat = file_path.stat()
                cached = self._preview_cache.get(cache_key)
                if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
                    return cached[2]
            except Exception:
                stat = None
        if not file_path or not file_path.exists():
            # If revised_content string exists
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
                "pdf_stream_url": None
            }

        rendered = self._render_file_to_preview(
            doc_id=ver.doc_id,
            filename=filename,
            cand_name=cand_name,
            file_path=file_path,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            version_id=version_id
        )
        if stat is not None:
            self._preview_cache[cache_key] = (stat.st_mtime, stat.st_size, rendered)
        return rendered

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
                import pypdf
                with open(file_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    if len(reader.pages) > 0:
                        is_real_pdf = True
                        for idx, p in enumerate(reader.pages):
                            p_text = p.extract_text() or ""
                            pages.append(self._format_pdf_page_html(p_text, idx + 1, cand_name))
            except Exception:
                # If mock pdf or text-based
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

    def _docx_to_pages(self, file_path: Path, cand_name: str) -> List[str]:
        import docx
        doc = docx.Document(str(file_path))
        pages: List[str] = []
        current_page_items: List[str] = []

        # Header banner on page 1
        current_page_items.append(
            f"<div class='doc-header-banner'>"
            f"<div class='doc-cand-name'>{html.escape(cand_name)}</div>"
            f"</div>"
        )

        item_count = 0
        MAX_ITEMS_PER_PAGE = 26

        def flush_page():
            nonlocal current_page_items, item_count
            if current_page_items:
                pages.append("\n".join(current_page_items))
                current_page_items = []
                item_count = 0

        for p in doc.paragraphs:
            text = p.text.strip()
            
            # Check for explicit page break in runs
            has_page_break = False
            for r in p.runs:
                if "\f" in r.text or "lastRenderedPageBreak" in r._element.xml or 'w:type="page"' in r._element.xml:
                    has_page_break = True
                    break

            if has_page_break and item_count > 0:
                flush_page()

            if not text:
                continue

            # Detect headings
            upper = text.upper()
            is_heading = (
                p.style.name.startswith("Heading") or
                upper in ["SUMMARY", "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "EXPERIENCE", "WORK EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS"]
            )

            p_html = self._format_paragraph_runs(p)

            if is_heading:
                if item_count >= (MAX_ITEMS_PER_PAGE - 6) and item_count > 0:
                    flush_page()
                current_page_items.append(f"<h3 class='doc-sec-heading'>{p_html}</h3>")
                item_count += 2
            else:
                # Check for bullet point
                if p.style.name.startswith("List") or text.startswith(("•", "-", "*")):
                    clean_text = re.sub(r'^[•\-\*]\s*', '', p_html)
                    current_page_items.append(f"<div class='doc-bullet-item'>&bull; {clean_text}</div>")
                else:
                    current_page_items.append(f"<p class='doc-para'>{p_html}</p>")
                item_count += 1

            if item_count >= MAX_ITEMS_PER_PAGE:
                flush_page()

        # Render tables
        for table in doc.tables:
            table_rows_html = []
            for row in table.rows:
                cells_html = [f"<td>{html.escape(c.text.strip())}</td>" for c in row.cells]
                table_rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
            current_page_items.append(f"<table class='doc-table'>{''.join(table_rows_html)}</table>")
            item_count += len(table.rows)
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
        
        if page_num == 1:
            html_lines.append(
                f"<div class='doc-header-banner'>"
                f"<div class='doc-cand-name'>{html.escape(cand_name)}</div>"
                f"</div>"
            )

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
