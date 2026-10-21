import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from app.config import settings, DMS_VERSIONS_DIR
from app.integrations.dms_adapter import dms_adapter

class WordResumeService:
    """
    Word Resume Generation & Formatting Preservation Engine.
    Preserves all existing resume content, structures, and details while incorporating improvements.
    Never strips out candidate content or reduces resumes to minimal summaries.
    """

    def __init__(self):
        self.versions_dir = DMS_VERSIONS_DIR
        self.versions_dir.mkdir(parents=True, exist_ok=True)

    def extract_docx_elements(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Extracts paragraphs and table cells from a DOCX file with stable element IDs,
        preserving paragraph indexes, run styles, and section mappings.
        """
        elements = []
        if not file_path or not Path(file_path).exists():
            return elements

        try:
            doc = docx.Document(str(file_path))
        except Exception:
            return elements

        current_section = "professional_summary"
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

        current_section = "professional_summary"
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
        original_path: Path,
        output_path: Path,
        approved_changes: List[Dict[str, Any]]
    ) -> bool:
        """
        Opens the original DOCX file, applies approved modifications directly to the targeted
        paragraphs and table cells while preserving existing styles, fonts, font sizes, colors,
        alignment, tables, headers, footers, and margins. Saves to output_path.
        """
        try:
            doc = docx.Document(str(original_path))
        except Exception:
            return False

        applied_count = 0
        for change in approved_changes:
            target_id = change.get("target_element_id", "")
            orig_text = change.get("original_text", "").strip()
            proposed_text = change.get("proposed_text", "").strip()
            if not proposed_text:
                continue

            target_p = None

            # 1. Try direct element ID matching for paragraph_N
            if target_id.startswith("paragraph_"):
                try:
                    p_idx = int(target_id.split("_")[1])
                    if p_idx < len(doc.paragraphs):
                        cand_p = doc.paragraphs[p_idx]
                        if not orig_text or (orig_text.lower() in cand_p.text.lower()) or (cand_p.text.strip() and len(cand_p.text) > 10):
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
                orig_lower = orig_text.lower()
                for p in doc.paragraphs:
                    p_lower = p.text.lower().strip()
                    if orig_lower in p_lower or (len(orig_lower) > 20 and orig_lower[:30] in p_lower):
                        target_p = p
                        break

            # 4. Search within tables if still not found
            if not target_p and orig_text:
                orig_lower = orig_text.lower()
                for t in doc.tables:
                    for row in t.rows:
                        for cell in row.cells:
                            for p in cell.paragraphs:
                                if orig_lower in p.text.lower():
                                    target_p = p
                                    break
                            if target_p:
                                break
                        if target_p:
                            break

            # If found, update text while preserving runs & typography
            if target_p:
                self._update_paragraph_preserving_runs(target_p, proposed_text)
                applied_count += 1

        doc.save(str(output_path))
        return applied_count > 0 or len(approved_changes) == 0

    def _update_paragraph_preserving_runs(self, p: docx.text.paragraph.Paragraph, new_text: str):
        """
        Updates paragraph text preserving run font family, font size, bold, italic, and color.
        """
        if not p.runs:
            p.text = new_text
            return

        # Check for bold lead-in pattern (e.g. "Python Development: Implemented...")
        if ":" in new_text and len(new_text.split(":", 1)[0]) < 40 and len(p.runs) >= 2:
            parts = new_text.split(":", 1)
            p.runs[0].text = parts[0] + ":"
            p.runs[0].bold = True
            p.runs[1].text = parts[1]
            p.runs[1].bold = False
            for r in p.runs[2:]:
                r.text = ""
        else:
            first_run = p.runs[0]
            first_run.text = new_text
            for r in p.runs[1:]:
                r.text = ""

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
          fonts, layout, tables, margins, and headers/footers.
        - For PDF/TXT files: Generates a professionally styled Word document with all sections intact.
        """
        output_path = self.versions_dir / f"{version_id}.docx"

        # Check if original document is a valid DOCX file for in-place editing
        if original_doc_path and Path(original_doc_path).exists() and Path(original_doc_path).suffix.lower() == ".docx":
            changes_to_apply = approved_changes or []
            # If no explicit change items but revised_content provided, attempt in-place parse
            if not changes_to_apply and revised_content:
                changes_to_apply = self._extract_changes_from_revised_content(original_doc_path, revised_content)

            try:
                success = self.apply_docx_changes_inplace(Path(original_doc_path), output_path, changes_to_apply)
                if success and output_path.exists():
                    return output_path
            except Exception:
                pass

        # Fallback / PDF adaptation: Build complete professional Word document
        doc = docx.Document()
        self._build_complete_docx_resume(doc, candidate_name, target_role, profile, revised_content, personal_overrides)
        doc.save(str(output_path))
        return output_path

    def _extract_changes_from_revised_content(self, original_path: Path, revised_content: str) -> List[Dict[str, Any]]:
        """
        Infers targeted changes by comparing paragraphs between original DOCX and revised content.
        """
        changes = []
        try:
            orig_doc = docx.Document(str(original_path))
            revised_lines = [l.strip() for l in revised_content.splitlines() if l.strip()]
            for i, p in enumerate(orig_doc.paragraphs):
                p_text = p.text.strip()
                if not p_text or len(p_text) < 15:
                    continue
                # Look for matching line in revised content that is modified
                for r_line in revised_lines:
                    clean_r = r_line.lstrip("-*• ").strip()
                    clean_p = p_text.lstrip("-*• ").strip()
                    if clean_r != clean_p and (clean_r[:20].lower() in clean_p.lower() or clean_p[:20].lower() in clean_r.lower()):
                        changes.append({
                            "target_element_id": f"paragraph_{i}",
                            "original_text": p_text,
                            "proposed_text": r_line
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

            clean_text = trimmed.lstrip("#").strip()

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
                doc.add_picture(io.BytesIO(img_bytes), width=Inches(3.5))
            elif Path(src).exists():
                doc.add_picture(src, width=Inches(3.5))
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

