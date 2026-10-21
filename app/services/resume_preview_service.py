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
    """

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

        file_path = dms_adapter.get_file_path(doc.dms_ref)
        if not file_path or not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File for document '{doc_id}' not found in storage.")

        cand_name = self.resolve_candidate_full_name(doc_id, doc.original_filename, db)
        return self._render_file_to_preview(
            doc_id=doc_id,
            filename=doc.original_filename,
            cand_name=cand_name,
            file_path=file_path,
            mime_type=doc.mime_type
        )

    def get_version_preview(self, version_id: str, db: Session) -> Dict[str, Any]:
        ver = db.query(ResumeVersion).filter(ResumeVersion.version_id == version_id).first()
        if not ver:
            raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

        file_path = dms_adapter.get_file_path(ver.dms_ref)
        doc = db.query(Document).filter(Document.doc_id == ver.doc_id).first()
        filename = f"{doc.original_filename.rsplit('.', 1)[0]}_v{version_id.split('-v')[-1]}.docx" if doc else f"{version_id}.docx"
        cand_name = self.resolve_candidate_full_name(ver.doc_id, filename, db)

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

        return self._render_file_to_preview(
            doc_id=ver.doc_id,
            filename=filename,
            cand_name=cand_name,
            file_path=file_path,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            version_id=version_id
        )

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
