import io
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from app.config import settings
from app.integrations.dms_adapter import dms_adapter

class WordResumeService:
    """
    Word Resume Generation & Formatting Preservation Engine.
    Preserves all existing resume content, structures, and details while incorporating improvements.
    Never strips out candidate content or reduces resumes to minimal summaries.
    """

    def __init__(self):
        pass

    def extract_docx_elements(self, file_source: Any) -> List[Dict[str, Any]]:
        """
        Extracts paragraphs and table cells from a DOCX file or in-memory bytes with stable element IDs,
        preserving paragraph indexes, run styles, and section mappings.
        """
        elements = []
        if not file_source:
            return elements

        try:
            if isinstance(file_source, (bytes, bytearray)):
                doc = docx.Document(io.BytesIO(bytes(file_source)))
            elif isinstance(file_source, io.BytesIO):
                doc = docx.Document(file_source)
            elif Path(file_source).exists():
                doc = docx.Document(str(file_source))
            else:
                return elements
        except Exception:
            return elements

        current_section = "personal_details"
        for i, p in enumerate(doc.paragraphs):
            text = p.text.strip()
            if not text:
                continue

            # Identify section transitions from headers
            upper = text.upper()
            if any(h in upper for h in ["SUMMARY", "PROFILE", "OBJECTIVE"]):
                current_section = "professional_summary"
                continue
            elif any(h in upper for h in ["SKILLS", "TECHNOLOGIES", "COMPETENCIES"]):
                current_section = "skills"
                continue
            elif any(h in upper for h in ["EXPERIENCE", "EMPLOYMENT", "WORK HISTORY"]):
                current_section = "professional_experience"
                continue
            elif any(h in upper for h in ["PROJECTS", "KEY PROJECTS", "ACADEMIC PROJECTS"]):
                current_section = "projects"
                continue
            elif any(h in upper for h in ["EDUCATION", "ACADEMIC BACKGROUND", "QUALIFICATIONS"]):
                current_section = "education"
                continue
            elif any(h in upper for h in ["CERTIFICATIONS", "LICENSES", "ACHIEVEMENTS"]):
                current_section = "certifications"
                continue

            elements.append({
                "element_id": f"paragraph_{i}",
                "index": i,
                "type": "paragraph",
                "section": current_section,
                "text": text,
                "style": p.style.name if p.style else "Normal",
                "runs_count": len(p.runs)
            })

        for t_idx, table in enumerate(doc.tables):
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    for p_idx, p in enumerate(cell.paragraphs):
                        text = p.text.strip()
                        if text:
                            elements.append({
                                "element_id": f"table_{t_idx}_r{r_idx}_c{c_idx}_p{p_idx}",
                                "type": "table_cell",
                                "section": current_section,
                                "text": text,
                                "table_index": t_idx,
                                "row": r_idx,
                                "col": c_idx,
                                "p_idx": p_idx
                            })

        return elements

    def extract_text_elements(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Extracts line-based elements from raw text (e.g. from PDF/TXT resumes).
        """
        elements = []
        if not raw_text:
            return elements

        current_section = "personal_details"
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            upper = line.upper()
            if any(h in upper for h in ["SUMMARY", "PROFILE", "OBJECTIVE"]):
                current_section = "professional_summary"
                continue
            elif any(h in upper for h in ["SKILLS", "TECHNOLOGIES", "COMPETENCIES"]):
                current_section = "skills"
                continue
            elif any(h in upper for h in ["EXPERIENCE", "EMPLOYMENT", "WORK HISTORY"]):
                current_section = "professional_experience"
                continue
            elif any(h in upper for h in ["PROJECTS", "KEY PROJECTS"]):
                current_section = "projects"
                continue
            elif any(h in upper for h in ["EDUCATION", "ACADEMIC"]):
                current_section = "education"
                continue

            elements.append({
                "element_id": f"paragraph_{i}",
                "index": i,
                "type": "paragraph",
                "section": current_section,
                "text": line
            })
        return elements

    def apply_docx_changes_inplace(
        self,
        original_source: Any,
        output_dest: Optional[Any] = None,
        approved_changes: Optional[List[Dict[str, Any]]] = None,
        revised_content: Optional[str] = None,
        personal_overrides: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Opens the original DOCX (from Path, file string, bytes, or BytesIO),
        applies approved modifications directly to the targeted paragraphs and table cells
        while strictly preserving existing styles, fonts, font sizes, colors, paragraph
        alignment, tables, headers, footers, embedded images, and margins.
        If output_dest is None or BytesIO, returns bytes without writing to disk.
        If output_dest is Path/str, saves to output_dest and returns True.
        """
        try:
            if isinstance(original_source, (bytes, bytearray)):
                doc = docx.Document(io.BytesIO(bytes(original_source)))
            elif isinstance(original_source, io.BytesIO):
                doc = docx.Document(original_source)
            elif Path(original_source).exists():
                doc = docx.Document(str(original_source))
            else:
                return False if output_dest else None
        except Exception:
            return False if output_dest else None

        if personal_overrides:
            po_name = personal_overrides.get("name")
            po_phone = personal_overrides.get("phone")
            po_email = personal_overrides.get("email")
            po_loc = personal_overrides.get("location")
            for p in doc.paragraphs[:10]:
                p_text = p.text
                if po_phone and re.search(r'(?:Phone|Mobile|Tel|Cell|Contact)?:?\s*(\+?\d[\d\s\-().]{8,20})', p_text, re.IGNORECASE):
                    self._update_paragraph_preserving_runs(p, re.sub(r'(\+?\d[\d\s\-().]{8,20})', po_phone, p_text))
                if po_email and re.search(r'[\w\.-]+@[\w\.-]+\.\w+', p_text):
                    self._update_paragraph_preserving_runs(p, re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', po_email, p_text))
            if po_name:
                for p in doc.paragraphs[:5]:
                    p_text_clean = p.text.strip()
                    if p_text_clean and len(p_text_clean.split()) <= 5 and not any(k in p_text_clean.upper() for k in ["RESUME", "CV", "SUMMARY", "EXPERIENCE", "SKILLS", "OBJECTIVE", "EMAIL", "PHONE", "@", "HTTP", ":", "|"]):
                        self._update_paragraph_preserving_runs(p, po_name.upper())
                        break
            po_role = personal_overrides.get("role")
            if po_role:
                for p in doc.paragraphs[1:6]:
                    p_txt = p.text.strip()
                    if p_txt and len(p_txt) < 60 and any(k in p_txt.lower() for k in ["developer", "engineer", "architect", "lead", "manager", "specialist", "administrator", "analyst"]):
                        self._update_paragraph_preserving_runs(p, po_role)
                        break

        def clean_norm(s: str) -> str:
            if not s:
                return ""
            s = re.sub(r'^[•\-\*\d\.\)\s]+', '', s)
            s = re.sub(r'\s+', ' ', s)
            return s.strip().lower()

        def text_similarity(s1: str, s2: str) -> float:
            c1 = clean_norm(s1)
            c2 = clean_norm(s2)
            if not c1 or not c2:
                return 0.0
            if c1 in c2 or c2 in c1:
                return 1.0
            w1 = set(c1.split())
            w2 = set(c2.split())
            if not w1 or not w2:
                return 0.0
            overlap = len(w1.intersection(w2))
            return overlap / max(len(w1), len(w2))

        applied_count = 0
        for change in approved_changes:
            target_id = change.get("target_element_id", "")
            orig_text = change.get("original_text", "").strip()
            proposed_text = change.get("proposed_text", "").strip()
            if not proposed_text:
                continue

            target_p = None

            # 1. Try direct element ID matching for paragraph_N if text similarity confirms
            if target_id.startswith("paragraph_"):
                try:
                    p_idx = int(target_id.split("_")[1])
                    if p_idx < len(doc.paragraphs):
                        cand_p = doc.paragraphs[p_idx]
                        if not orig_text or text_similarity(orig_text, cand_p.text) > 0.4 or clean_norm(orig_text)[:20] in clean_norm(cand_p.text):
                            target_p = cand_p
                except (ValueError, IndexError):
                    pass

            # 2. Try table cell matching
            if not target_p and target_id.startswith("table_"):
                parts = target_id.split("_")
                try:
                    t_idx = int(parts[1])
                    r_idx = int(parts[2][1:])
                    c_idx = int(parts[3][1:])
                    p_idx = int(parts[4][1:])
                    target_p = doc.tables[t_idx].rows[r_idx].cells[c_idx].paragraphs[p_idx]
                except (ValueError, IndexError):
                    pass

            # 3. Fuzzy/content search across all paragraphs if not matched by ID
            if not target_p and orig_text:
                best_p = None
                best_sim = 0.0
                for p in doc.paragraphs:
                    sim = text_similarity(orig_text, p.text)
                    if sim > best_sim:
                        best_sim = sim
                        best_p = p
                if best_p and best_sim >= 0.4:
                    target_p = best_p

            # 4. Search within tables if still not found
            if not target_p and orig_text:
                best_tp = None
                best_tsim = 0.0
                for t in doc.tables:
                    for row in t.rows:
                        for cell in row.cells:
                            for p in cell.paragraphs:
                                sim = text_similarity(orig_text, p.text)
                                if sim > best_tsim:
                                    best_tsim = sim
                                    best_tp = p
                if best_tp and best_tsim >= 0.4:
                    target_p = best_tp

            # 5. If found, update text while strictly preserving runs, images, fonts & alignment
            if target_p:
                self._update_paragraph_preserving_runs(target_p, proposed_text)
                applied_count += 1
            # If target element is not found, leave document structure and existing content strictly unchanged.
            # Do NOT append to the end of the document.

        # Apply candidate contact and personal details overrides to header paragraphs
        if personal_overrides:
            new_name = (personal_overrides.get("name") or personal_overrides.get("candidate_name") or "").strip()
            new_email = (personal_overrides.get("email") or personal_overrides.get("candidate_email") or "").strip()
            new_phone = (personal_overrides.get("phone") or personal_overrides.get("candidate_phone") or "").strip()
            new_role = (personal_overrides.get("role") or personal_overrides.get("candidate_role") or "").strip()
            new_loc = (personal_overrides.get("location") or personal_overrides.get("candidate_location") or "").strip()

            if new_name:
                for idx in range(min(5, len(doc.paragraphs))):
                    p = doc.paragraphs[idx]
                    p_text = p.text.strip()
                    if p_text and len(p_text) < 60 and "@" not in p_text and not re.search(r'\d{5,}', p_text):
                        if p_text.upper() not in ["RESUME", "CURRICULUM VITAE", "CV", "PROFILE", "SUMMARY"]:
                            self._update_paragraph_preserving_runs(p, new_name)
                            break

            for idx in range(min(10, len(doc.paragraphs))):
                p = doc.paragraphs[idx]
                p_text = p.text
                if not p_text.strip():
                    continue
                updated_text = p_text
                if new_email and "@" in p_text:
                    updated_text = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', new_email, updated_text)
                if new_phone and re.search(r'(\+?\d[\d\s\-\(\)]{8,15}\d)', p_text):
                    updated_text = re.sub(r'(\+?\d[\d\s\-\(\)]{8,15}\d)', new_phone, updated_text)
                if new_role and idx in [1, 2] and len(p_text.strip()) < 50 and "@" not in p_text and not re.search(r'\d', p_text):
                    if any(t in p_text.lower() for t in ["engineer", "developer", "architect", "manager", "lead", "specialist"]):
                        updated_text = new_role
                if updated_text != p_text:
                    self._update_paragraph_preserving_runs(p, updated_text)

        # Embed any newly added pictures from revised_content (e.g. editor canvas)
        if revised_content and "data:image" in revised_content:
            self._embed_canvas_images(doc, revised_content)

        if output_dest is None:
            buf = io.BytesIO()
            doc.save(buf)
            return buf.getvalue()
        elif isinstance(output_dest, io.BytesIO):
            doc.save(output_dest)
            return output_dest.getvalue()
        else:
            doc.save(str(output_dest))
            return True

    def _update_paragraph_preserving_runs(self, p: docx.text.paragraph.Paragraph, new_text: str):
        """
        Updates paragraph text preserving run font family, font size, bold, italic, and color,
        while strictly preserving any embedded drawings, images, shapes, or fields,
        AND preserving paragraph alignment (JUSTIFY, CENTER, LEFT, RIGHT) and spacing.
        """
        saved_alignment = p.alignment
        saved_space_before = p.paragraph_format.space_before
        saved_space_after = p.paragraph_format.space_after
        saved_line_spacing = p.paragraph_format.line_spacing

        # Clean unintended Markdown heading hashes (e.g. "### ", "## ", "# ")
        # while strictly preserving valid terms like "C#", "F#", or "#1"
        clean_text = re.sub(r'^(?:#{1,6}\s+)', '', new_text)
        clean_text = re.sub(r'\*\*(.*?)\*\*', r'\1', clean_text)
        new_text = clean_text

        if not p.runs:
            p.text = new_text
            p.alignment = saved_alignment
            return

        # Check if any run contains drawing or image elements
        runs_with_drawings = set()
        for i, r in enumerate(p.runs):
            if r._element.xpath('.//w:drawing | .//w:pict | .//w:object'):
                runs_with_drawings.add(i)

        # Filter runs where text can be safely set
        available_text_runs = [r for i, r in enumerate(p.runs) if i not in runs_with_drawings]

        if not available_text_runs:
            # If all runs have drawings, append a new run for the text without removing images
            new_run = p.add_run(new_text)
            p.alignment = saved_alignment
            return

        # Check for bold lead-in pattern (e.g. "Core Competencies: ...")
        if ":" in new_text and len(new_text.split(":", 1)[0]) < 40 and len(available_text_runs) >= 2:
            parts = new_text.split(":", 1)
            available_text_runs[0].text = parts[0] + ":"
            available_text_runs[0].bold = True
            available_text_runs[1].text = parts[1]
            available_text_runs[1].bold = False
            for r in available_text_runs[2:]:
                r.text = ""
        else:
            available_text_runs[0].text = new_text
            for r in available_text_runs[1:]:
                r.text = ""

        # Strictly restore original paragraph alignment and formatting
        p.alignment = saved_alignment
        if saved_space_before is not None:
            p.paragraph_format.space_before = saved_space_before
        if saved_space_after is not None:
            p.paragraph_format.space_after = saved_space_after
        if saved_line_spacing is not None:
            p.paragraph_format.line_spacing = saved_line_spacing

    def generate_improved_docx(
        self,
        doc_id: str,
        version_id: str,
        candidate_name: str,
        target_role: str,
        profile: Dict[str, Any],
        revised_content: str,
        original_doc_path: Optional[Path] = None,
        personal_overrides: Optional[Dict[str, Any]] = None,
        approved_changes: Optional[List[Dict[str, Any]]] = None
    ) -> Path:
        """
        Creates an improved Microsoft Word (.docx) resume.
        - For original DOCX files: Edits the original document in-place preserving styles,
          fonts, layout, tables, margins, embedded images, and headers/footers.
          NEVER replaces or destroys original DOCX alignment.
        - For PDF/TXT files: Generates a professionally styled Word document with all sections intact.
        """
        output_path = self.versions_dir / f"{version_id}.docx"

        # Check if original document is a valid DOCX file for in-place editing
        if original_doc_path and Path(original_doc_path).exists() and Path(original_doc_path).suffix.lower() == ".docx":
            changes_to_apply = list(approved_changes or [])
            # Also extract any user manual edits from revised_content (e.g. from the Word Editor canvas)
            if revised_content:
                manual_changes = self._extract_changes_from_revised_content(original_doc_path, revised_content)
                # Combine without duplicate paragraphs
                for mc in manual_changes:
                    if not any(ac.get("target_element_id") == mc.get("target_element_id") for ac in changes_to_apply):
                        changes_to_apply.append(mc)

            try:
                self.apply_docx_changes_inplace(Path(original_doc_path), output_path, changes_to_apply, revised_content=revised_content)
                if output_path.exists():
                    return output_path
            except Exception:
                # If error, copy original directly to output_path so layout and images are NEVER lost!
                import shutil
                shutil.copyfile(str(original_doc_path), str(output_path))
                return output_path

        # Fallback / PDF adaptation: Build complete professional Word document
        doc = docx.Document()
        self._build_complete_docx_resume(doc, candidate_name, target_role, profile, revised_content, personal_overrides)
        if revised_content and "data:image" in revised_content:
            self._embed_canvas_images(doc, revised_content)
        doc.save(str(output_path))
        return output_path

    def generate_improved_docx_bytes(
        self,
        candidate_name: str,
        target_role: str,
        profile: Dict[str, Any],
        revised_content: str,
        original_doc_bytes: Optional[bytes] = None,
        personal_overrides: Optional[Dict[str, Any]] = None,
        approved_changes: Optional[List[Dict[str, Any]]] = None
    ) -> bytes:
        """
        Creates an improved DOCX entirely in-memory as bytes without touching local disk.
        If original_doc_bytes is provided and is a valid DOCX, edits in-place preserving styles,
        fonts, tables, margins, embedded images, and layouts.
        """
        if original_doc_bytes and original_doc_bytes.startswith(b"PK\x03\x04"):
            changes_to_apply = list(approved_changes or [])
            try:
                result_bytes = self.apply_docx_changes_inplace(
                    original_source=original_doc_bytes,
                    output_dest=None,
                    approved_changes=changes_to_apply,
                    revised_content=revised_content,
                    personal_overrides=personal_overrides
                )
                if result_bytes and isinstance(result_bytes, (bytes, bytearray)):
                    # Validate that generated DOCX opens structurally
                    test_doc = docx.Document(io.BytesIO(bytes(result_bytes)))
                    if len(test_doc.paragraphs) > 0 or len(test_doc.tables) > 0:
                        return bytes(result_bytes)
            except Exception as e:
                logger.warning(f"In-place DOCX modification warning: {e}")

        # Fallback / PDF adaptation: Build complete professional Word document in-memory
        doc = docx.Document()
        self._build_complete_docx_resume(doc, candidate_name, target_role, profile, revised_content, personal_overrides)
        if revised_content and "data:image" in revised_content:
            self._embed_canvas_images(doc, revised_content)
        buf = io.BytesIO()
        doc.save(buf)
        out_bytes = buf.getvalue()
        # Validate generated DOCX
        docx.Document(io.BytesIO(out_bytes))
        return out_bytes

    def _embed_canvas_images(self, doc: docx.Document, content: str):
        """
        Extracts base64 or inline images inserted into the editor canvas and embeds them into the Word document,
        strictly preserving their placement (e.g. top-right profile photo, top-left, or body) and width.
        """
        import base64
        import io
        import re
        from docx.shared import Inches, Pt
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "html.parser")
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if not src:
                    continue
                if src.startswith("data:image"):
                    try:
                        _, b64_str = src.split(",", 1)
                        img_bytes = base64.b64decode(b64_str.strip())
                        wrapper = img.find_parent("div", class_="resizable-image-wrapper")

                        # Determine alignment and placement
                        align = ""
                        width_in = 1.6
                        if wrapper:
                            align = (wrapper.get("data-align") or "").lower()
                            style = wrapper.get("style", "")
                            
                            # Parse width if set
                            w_match = re.search(r'width\s*:\s*(\d+)px', img.get("style", "") + " " + style)
                            if w_match:
                                px = int(w_match.group(1))
                                width_in = max(0.8, min(4.0, round(px / 96.0, 2)))
                            
                            # If no explicit data-align, infer from position style
                            if not align and style:
                                top_match = re.search(r'top\s*:\s*(\d+)px', style)
                                left_match = re.search(r'left\s*:\s*(\d+)px', style)
                                right_match = re.search(r'right\s*:\s*(\d+)px', style)
                                
                                top_val = int(top_match.group(1)) if top_match else 0
                                left_val = int(left_match.group(1)) if left_match else None
                                is_right = "right" in style or (left_val is not None and left_val > 350)
                                
                                if top_val < 300:
                                    align = "top-right" if is_right else "top-left"
                                else:
                                    align = "center"
                        
                        if not align:
                            align = "top-right"

                        # Insert paragraph at top for header photo (top-right or top-left)
                        if align in ["top-right", "top-left"]:
                            if doc.paragraphs and len(doc.paragraphs) > 0:
                                p = doc.paragraphs[0].insert_paragraph_before()
                            else:
                                p = doc.add_paragraph()
                            
                            p.alignment = (docx.enum.text.WD_ALIGN_PARAGRAPH.RIGHT 
                                           if "right" in align 
                                           else docx.enum.text.WD_ALIGN_PARAGRAPH.LEFT)
                            p.paragraph_format.space_before = Pt(0)
                            p.paragraph_format.space_after = Pt(4)
                            run = p.add_run()
                            run.add_picture(io.BytesIO(img_bytes), width=Inches(width_in))
                        else:
                            # Inline / body placement
                            p = doc.add_paragraph()
                            p.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
                            p.paragraph_format.space_before = Pt(6)
                            p.paragraph_format.space_after = Pt(6)
                            run = p.add_run()
                            run.add_picture(io.BytesIO(img_bytes), width=Inches(width_in))
                    except Exception:
                        pass
        except Exception:
            pass

    def _extract_changes_from_revised_content(self, original_path: Path, revised_content: str) -> List[Dict[str, Any]]:
        """
        Infers targeted changes by comparing paragraphs between original DOCX and revised content.
        Preserves original document layout and all untouched paragraphs.
        """
        changes = []
        try:
            from bs4 import BeautifulSoup
            if "<" in revised_content and ">" in revised_content:
                soup = BeautifulSoup(revised_content, "html.parser")
                # Remove header block if present
                for hdr in soup.find_all("div", class_="resume-header-block"):
                    hdr.decompose()
                revised_lines = [tag.get_text().strip() for tag in soup.find_all(["p", "li", "h1", "h2", "h3", "h4", "div"]) if tag.get_text().strip()]
            else:
                revised_lines = [l.strip() for l in revised_content.splitlines() if l.strip()]

            orig_doc = docx.Document(str(original_path))
            for i, p in enumerate(orig_doc.paragraphs):
                p_text = p.text.strip()
                if not p_text or len(p_text) < 10:
                    continue
                # Look for matching line in revised content that is modified
                for r_line in revised_lines:
                    clean_r = re.sub(r'^[•\-\*]\s*', '', r_line).strip()
                    clean_r = re.sub(r'^(?:#{1,6}\s+)', '', clean_r).strip()
                    clean_r = re.sub(r'\*\*(.*?)\*\*', r'\1', clean_r).strip()
                    clean_p = re.sub(r'^[•\-\*]\s*', '', p_text).strip()
                    if clean_r and clean_p and clean_r != clean_p:
                        # Check partial similarity or token overlap
                        words_p = set(clean_p.lower().split())
                        words_r = set(clean_r.lower().split())
                        if words_p and words_r:
                            overlap = len(words_p.intersection(words_r)) / max(len(words_p), len(words_r))
                            if overlap >= 0.3 or clean_r[:18].lower() in clean_p.lower() or clean_p[:18].lower() in clean_r.lower():
                                changes.append({
                                    "target_element_id": f"paragraph_{i}",
                                    "original_text": p_text,
                                    "proposed_text": clean_r
                                })
                                break
        except Exception:
            pass
        return changes

    def _build_complete_docx_resume(
        self,
        doc: docx.Document,
        candidate_name: str,
        target_role: str,
        profile: Dict[str, Any],
        revised_content: str,
        personal_overrides: Optional[Dict[str, Any]] = None
    ):
        """
        Builds a comprehensive, high-quality Microsoft Word resume.
        Renders candidate's personal details header (Name, Role, Phone, Email, Location, Links)
        followed by all enhanced sections with modern corporate formatting and typography.
        """
        # Standard 0.75" Margins
        for s in doc.sections:
            s.top_margin = Inches(0.75)
            s.bottom_margin = Inches(0.75)
            s.left_margin = Inches(0.75)
            s.right_margin = Inches(0.75)

        po = personal_overrides or {}
        resolved_name = (po.get("name") or candidate_name or "Candidate Professional").strip()
        resolved_role = (po.get("role") or target_role or "").strip()
        resolved_phone = (po.get("phone") or "").strip()
        resolved_email = (po.get("email") or "").strip()
        resolved_loc = (po.get("location") or "").strip()
        resolved_links = (po.get("links") or "").strip()

        # Sanitize resolved_name if it is a section heading
        invalid_names = {"SUMMARY", "OBJECTIVE", "PROFILE", "RESUME", "CURRICULUM VITAE", "CV", "CANDIDATE"}
        if resolved_name.upper() in invalid_names:
            clean = re.sub(r'[\-_.]*(?:ATS|Resume|CV|Optimized|Final|\d+|\([0-9]+\))*\.(?:pdf|docx|doc|txt)$', '', candidate_name, flags=re.IGNORECASE)
            clean = re.sub(r'[\-_]+', ' ', clean).strip()
            words = [w for w in clean.split() if w.lower() not in ['resume', 'cv', 'final', 'resumee', 'sfdc', 'developer', 'engineer', 'vault', 'qmsqdocs', 'qa', 'salesforce', 'se']]
            resolved_name = ' '.join(words).title() if words else (clean.title() if clean else "Candidate Professional")

        # Fallback to extracting from revised_content top lines if not provided in overrides
        if not resolved_phone or not resolved_email or not resolved_loc or not resolved_links:
            top_lines = revised_content.splitlines()[:10]
            for tl in top_lines:
                t_str = tl.strip().lstrip("#").strip()
                if not resolved_phone:
                    pm = re.search(r'Phone:\s*([^\s|]+)', t_str, re.IGNORECASE) or re.search(r'(\+?\d[\d\s\-\(\)]{8,15}\d)', t_str)
                    if pm:
                        p_cand = pm.group(1).strip()
                        if not re.match(r'^\d{4}\s*-\s*\d{4}$', p_cand):
                            resolved_phone = p_cand
                if not resolved_email:
                    em = re.search(r'Email:\s*([^\s|]+)', t_str, re.IGNORECASE) or re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', t_str)
                    if em:
                        resolved_email = em.group(1).strip()
                if not resolved_loc:
                    lm = re.search(r'Location:\s*([^|\n]+)', t_str, re.IGNORECASE) or re.search(r'Address:\s*([^|\n]+)', t_str, re.IGNORECASE)
                    if lm:
                        resolved_loc = lm.group(1).strip()
                if not resolved_links:
                    if any(k in t_str.lower() for k in ["linkedin", "github", "portfolio", "http"]):
                        if len(t_str) < 90 and not any(w in t_str.lower() for w in ["developed", "built", "using", "experience"]):
                            resolved_links = t_str

        # Build contact items
        contact_items = []
        if resolved_phone:
            contact_items.append(f"Phone: {resolved_phone}" if not resolved_phone.lower().startswith("phone") else resolved_phone)
        if resolved_email:
            contact_items.append(f"Email: {resolved_email}" if not resolved_email.lower().startswith("email") else resolved_email)
        if resolved_loc:
            contact_items.append(f"Location: {resolved_loc}" if not resolved_loc.lower().startswith("location") else resolved_loc)
        resolved_contact_line = " | ".join(contact_items)

        # 1. Candidate Name Header (Calibri 20pt Bold Centered)
        p_name = doc.add_paragraph()
        p_name.paragraph_format.space_before = Pt(0)
        p_name.paragraph_format.space_after = Pt(2)
        p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_name = p_name.add_run(resolved_name.upper())
        r_name.bold = True
        r_name.font.name = "Calibri"
        r_name.font.size = Pt(20)
        r_name.font.color.rgb = RGBColor(15, 23, 42)

        # 2. Professional Headline / Target Role (Calibri 11.5pt Bold Centered)
        if resolved_role:
            p_role = doc.add_paragraph()
            p_role.paragraph_format.space_before = Pt(0)
            p_role.paragraph_format.space_after = Pt(3)
            p_role.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r_role = p_role.add_run(resolved_role.upper())
            r_role.bold = True
            r_role.font.name = "Calibri"
            r_role.font.size = Pt(11.5)
            r_role.font.color.rgb = RGBColor(30, 64, 175)

        # 3. Contact Details (Phone | Email | Location)
        if resolved_contact_line:
            p_cont = doc.add_paragraph()
            p_cont.paragraph_format.space_before = Pt(0)
            p_cont.paragraph_format.space_after = Pt(2)
            p_cont.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r_cont = p_cont.add_run(resolved_contact_line)
            r_cont.font.name = "Calibri"
            r_cont.font.size = Pt(10)
            r_cont.font.color.rgb = RGBColor(71, 85, 105)

        # 4. Links / Portfolio
        if resolved_links:
            p_lnk = doc.add_paragraph()
            p_lnk.paragraph_format.space_before = Pt(0)
            p_lnk.paragraph_format.space_after = Pt(8)
            p_lnk.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r_lnk = p_lnk.add_run(resolved_links)
            r_lnk.font.name = "Calibri"
            r_lnk.font.size = Pt(9.5)
            r_lnk.font.color.rgb = RGBColor(37, 99, 235)

        # Common section heading keywords
        heading_keywords = [
            "summary", "objective", "profile", "professional summary", "executive summary",
            "experience", "work experience", "employment history", "professional experience",
            "internship experience", "internships", "training",
            "education", "academic background", "qualifications", "credentials",
            "skills", "technical skills", "core competencies", "technologies", "proficiencies",
            "projects", "key projects", "notable projects", "academic projects", "relevant project experience",
            "certifications", "achievements", "publications", "awards", "languages", "volunteering"
        ]

        lines = [line.rstrip() for line in revised_content.split("\n")]
        # Skip leading header lines from text body if they duplicate the personal details already rendered above
        start_idx = 0
        for i, l in enumerate(lines[:10]):
            trimmed = l.strip().lstrip("#").strip()
            if not trimmed:
                start_idx = i + 1
                continue
            is_dup_header = (
                trimmed.upper() == resolved_name.upper() or
                (resolved_role and trimmed.upper() == resolved_role.upper()) or
                any(k in trimmed.lower() for k in ["phone:", "email:", "location:"]) or
                (resolved_links and trimmed.lower() == resolved_links.lower()) or
                (any(c in trimmed for c in ["@", "linkedin.com", "github.com"]) and len(trimmed) < 80)
            )
            if is_dup_header:
                start_idx = i + 1
            else:
                break

        body_lines = lines[start_idx:]
        for line in body_lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            clean_text = re.sub(r'^(?:#{1,6}\s+)', '', trimmed).strip()

            # Check if section header
            lower_clean = clean_text.lower().rstrip(":")
            is_section_header = (
                trimmed.startswith("# ") or trimmed.startswith("## ") or
                (clean_text.isupper() and len(clean_text) < 45 and not clean_text.startswith("-")) or
                lower_clean in heading_keywords or
                (any(lower_clean == kw or lower_clean.startswith(f"{kw}:") for kw in heading_keywords) and len(clean_text) < 50)
            )

            if is_section_header:
                p_sec = doc.add_paragraph()
                p_sec.paragraph_format.space_before = Pt(12)
                p_sec.paragraph_format.space_after = Pt(4)
                p_sec.paragraph_format.keep_with_next = True
                r_sec = p_sec.add_run(clean_text.upper().rstrip(":"))
                r_sec.bold = True
                r_sec.font.name = "Calibri"
                r_sec.font.size = Pt(11.5)
                r_sec.font.color.rgb = RGBColor(30, 64, 175)
                continue

            # Check if bullet item
            if trimmed.startswith("- ") or trimmed.startswith("* ") or trimmed.startswith("• "):
                bullet_text = trimmed[2:].strip()
                p_b = doc.add_paragraph(style='List Bullet')
                p_b.paragraph_format.space_after = Pt(3)
                p_b.paragraph_format.line_spacing = 1.15
                
                # Check for bold lead-in (e.g. "Python Development: Created...")
                if ":" in bullet_text and len(bullet_text.split(":", 1)[0]) < 35:
                    label, desc = bullet_text.split(":", 1)
                    r_lbl = p_b.add_run(label + ":")
                    r_lbl.bold = True
                    r_lbl.font.name = "Calibri"
                    r_lbl.font.size = Pt(10)
                    r_desc = p_b.add_run(desc)
                    r_desc.font.name = "Calibri"
                    r_desc.font.size = Pt(10)
                else:
                    r_b = p_b.add_run(bullet_text)
                    r_b.font.name = "Calibri"
                    r_b.font.size = Pt(10)
                continue

            # Check if job title / company / date line (e.g. bold subhead)
            is_subhead = (
                len(trimmed) < 70 and
                (any(char.isdigit() for char in trimmed) and ("20" in trimmed or "19" in trimmed or "present" in trimmed.lower())) or
                any(title_word in trimmed.lower() for title_word in ["developer", "engineer", "lead", "architect", "manager", "analyst", "consultant", "intern", "specialist"])
            )

            if is_subhead:
                p_sub = doc.add_paragraph()
                p_sub.paragraph_format.space_before = Pt(6)
                p_sub.paragraph_format.space_after = Pt(2)
                p_sub.paragraph_format.keep_with_next = True
                r_sub = p_sub.add_run(trimmed)
                r_sub.bold = True
                r_sub.font.name = "Calibri"
                r_sub.font.size = Pt(10.5)
                r_sub.font.color.rgb = RGBColor(30, 41, 59)
                continue

            # Standard body paragraph
            p_body = doc.add_paragraph()
            p_body.paragraph_format.space_before = Pt(0)
            p_body.paragraph_format.space_after = Pt(4)
            p_body.paragraph_format.line_spacing = 1.15
            r_body = p_body.add_run(trimmed)
            r_body.font.name = "Calibri"
            r_body.font.size = Pt(10)

    def generate_rich_docx(
        self,
        doc_id: str,
        version_id: str,
        candidate_name: str,
        target_role: str,
        content_html_or_text: str,
        personal_overrides: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Builds a Microsoft Word (.docx) document from rich HTML or text,
        supporting headers, bold/italic/underline, bullet/numbered lists,
        text alignments, and embedded base64/URL images.
        """
        import io
        import base64
        from bs4 import BeautifulSoup, NavigableString, Tag

        output_path = self.versions_dir / f"{version_id}.docx"
        doc = docx.Document()

        # Set 0.75" margins
        for s in doc.sections:
            s.top_margin = Inches(0.75)
            s.bottom_margin = Inches(0.75)
            s.left_margin = Inches(0.75)
            s.right_margin = Inches(0.75)

        raw_str = (content_html_or_text or "").strip()
        is_html = "<" in raw_str and (">" in raw_str) and any(tag in raw_str.lower() for tag in ["<p", "<div", "<h1", "<h2", "<h3", "<img", "<ul", "<ol", "<span", "<strong", "<b"])

        if not is_html:
            self._build_complete_docx_resume(doc, candidate_name, target_role, {}, raw_str, personal_overrides)
            doc.save(str(output_path))
            return output_path

        soup = BeautifulSoup(raw_str, "html.parser")
        body = soup.body if soup.body else soup
        blocks = body.find_all(["h1", "h2", "h3", "h4", "p", "div", "ul", "ol", "img", "table"], recursive=False)
        if not blocks:
            blocks = list(body.children)

        for block in blocks:
            if isinstance(block, NavigableString):
                txt = str(block).strip()
                if txt:
                    p = doc.add_paragraph()
                    r = p.add_run(txt)
                    r.font.name = "Calibri"
                    r.font.size = Pt(10)
                continue

            tag_name = getattr(block, "name", "").lower()
            if not tag_name:
                continue

            if tag_name in ["h1", "h2", "h3", "h4"]:
                p = doc.add_paragraph()
                p.paragraph_format.keep_with_next = True
                if tag_name == "h1":
                    p.paragraph_format.space_before = Pt(12)
                    p.paragraph_format.space_after = Pt(4)
                    size = Pt(18)
                    color = RGBColor(15, 23, 42)
                elif tag_name == "h2":
                    p.paragraph_format.space_before = Pt(10)
                    p.paragraph_format.space_after = Pt(3)
                    size = Pt(13)
                    color = RGBColor(37, 99, 235)
                else:
                    p.paragraph_format.space_before = Pt(6)
                    p.paragraph_format.space_after = Pt(2)
                    size = Pt(11)
                    color = RGBColor(51, 65, 85)

                align = block.get("style", "").lower()
                if "center" in align:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif "right" in align:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

                r = p.add_run(block.get_text().strip())
                r.bold = True
                r.font.name = "Calibri"
                r.font.size = size
                r.font.color.rgb = color

            elif tag_name == "img":
                src = block.get("src", "")
                self._add_image_to_doc(doc, src)

            elif tag_name in ["ul", "ol"]:
                for li in block.find_all("li"):
                    style_name = 'List Bullet' if tag_name == "ul" else 'List Number'
                    p = doc.add_paragraph(style=style_name)
                    p.paragraph_format.space_after = Pt(2)
                    p.paragraph_format.line_spacing = 1.15
                    self._add_formatted_runs(p, li, base_size=Pt(10))

            elif tag_name in ["p", "div"]:
                images_in_p = block.find_all("img")
                if images_in_p and not block.get_text().strip():
                    for im in images_in_p:
                        self._add_image_to_doc(doc, im.get("src", ""))
                    continue

                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(4)
                p.paragraph_format.line_spacing = 1.15

                style_attr = block.get("style", "").lower()
                if "center" in style_attr:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif "right" in style_attr:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

                self._add_formatted_runs(p, block, base_size=Pt(10))

            elif tag_name == "table":
                rows = block.find_all("tr")
                if rows:
                    max_cols = max((len(r.find_all(["td", "th"])) for r in rows), default=1)
                    doc_table = doc.add_table(rows=len(rows), cols=max_cols)
                    doc_table.style = 'Table Grid'
                    for r_idx, tr in enumerate(rows):
                        cells = tr.find_all(["td", "th"])
                        for c_idx, cell in enumerate(cells):
                            if c_idx < max_cols:
                                cell_p = doc_table.cell(r_idx, c_idx).paragraphs[0]
                                cell_p.paragraph_format.space_before = Pt(2)
                                cell_p.paragraph_format.space_after = Pt(2)
                                is_th = cell.name.lower() == "th"
                                self._add_formatted_runs(cell_p, cell, base_size=Pt(9.5))
                                if is_th:
                                    for r in cell_p.runs:
                                        r.bold = True

        doc.save(str(output_path))
        return output_path

    def _add_image_to_doc(self, doc, src: str):
        import io
        import base64
        if not src:
            return
        try:
            if src.startswith("data:image"):
                head, b64_data = src.split(",", 1)
                img_bytes = base64.b64decode(b64_data)
                doc.add_picture(io.BytesIO(img_bytes), width=Inches(1.6))
            elif Path(src).exists():
                doc.add_picture(src, width=Inches(1.6))
        except Exception:
            pass

    def _add_formatted_runs(self, paragraph, container_tag, base_size=Pt(10)):
        from bs4 import NavigableString, Tag
        for child in container_tag.children:
            if isinstance(child, NavigableString):
                txt = str(child)
                if txt:
                    r = paragraph.add_run(txt)
                    r.font.name = "Calibri"
                    r.font.size = base_size
            elif isinstance(child, Tag):
                tag = child.name.lower()
                if tag == "img":
                    self._add_image_to_doc(paragraph._parent, child.get("src", ""))
                    continue
                txt = child.get_text()
                if txt:
                    r = paragraph.add_run(txt)
                    r.font.name = "Calibri"
                    r.font.size = base_size
                    if tag in ["b", "strong"]:
                        r.bold = True
                    if tag in ["i", "em"]:
                        r.italic = True
                    if tag == "u":
                        r.underline = True

word_resume_service = WordResumeService()

