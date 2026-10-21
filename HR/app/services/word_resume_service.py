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

    def generate_improved_docx(
        self,
        doc_id: str,
        version_id: str,
        candidate_name: str,
        target_role: str,
        profile: Dict[str, Any],
        revised_content: str,
        original_doc_path: Optional[Path] = None,
        personal_overrides: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Creates an improved Microsoft Word (.docx) resume.
        Converts the full revised resume text into a professionally styled Word document,
        incorporating candidate personal details in the header.
        """
        output_path = self.versions_dir / f"{version_id}.docx"

        doc = docx.Document()
        self._build_complete_docx_resume(doc, candidate_name, target_role, profile, revised_content, personal_overrides)
        doc.save(str(output_path))
        return output_path

    def _apply_inplace_improvements(
        self,
        doc: docx.Document,
        target_role: str,
        revised_content: str,
        profile: Dict[str, Any]
    ):
        """
        Preserves the entire original Word document structure, formatting, tables, and styles,
        modifying existing content and incorporating enhancements without deleting original sections.
        """
        # Look for suggested rewrite blocks or specific targeted modifications in revised_content
        additions = []
        for line in revised_content.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("- ") or line.startswith("* ") or line.startswith("• "):
                clean_bullet = line[2:].strip()
                # Check if this bullet already exists in original paragraphs
                already_in_doc = any(clean_bullet.lower() in p.text.lower() for p in doc.paragraphs)
                if not already_in_doc and len(clean_bullet) > 15:
                    additions.append(clean_bullet)

        # If there are net-new additions/enhancements, append a focused section to highlight alignment
        if additions and len(additions) <= 10:
            p_head = doc.add_paragraph()
            p_head.paragraph_format.space_before = Pt(14)
            p_head.paragraph_format.space_after = Pt(4)
            p_head.paragraph_format.keep_with_next = True
            r_head = p_head.add_run(f"TARGET ROLE ALIGNMENT & KEY HIGHLIGHTS: {target_role.upper()}")
            r_head.bold = True
            r_head.font.name = "Calibri"
            r_head.font.size = Pt(11)
            r_head.font.color.rgb = RGBColor(30, 64, 175)

            for item in additions:
                p_item = doc.add_paragraph(style='List Bullet')
                p_item.paragraph_format.space_after = Pt(3)
                p_item.paragraph_format.line_spacing = 1.15
                r_item = p_item.add_run(item)
                r_item.font.name = "Calibri"
                r_item.font.size = Pt(10)

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

word_resume_service = WordResumeService()
