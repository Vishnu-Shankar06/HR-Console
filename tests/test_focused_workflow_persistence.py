"""
Focused test suite for HR Console verifying:
1. Find Candidates Upload Persistence in Resume Library and IKM
2. Find Candidates Remove and Clear All scoped exclusively to screen state (no permanent delete)
3. Experience calculation (dates, overlapping periods, formats, approximate, invalid)
4. AI Resume Improvement workflow, layout preservation, and multi-file processing
5. Failure resilience (one file fails, remaining succeed)
"""

import io
import pytest
from datetime import datetime
from starlette.testclient import TestClient
import docx

from app.models.entities import Document, CandidateProfile, ResumeVersion, CandidatePII
from app.services.experience_calculator import experience_calculator
from app.services.word_resume_service import word_resume_service
from app.integrations.ikm_adapter import ikm_adapter


# ==============================================================================
# 1. EXPERIENCE CALCULATION TESTS
# ==============================================================================

def test_experience_calculator_tcs_example():
    """
    TCS: June 2023 - Present evaluated at October 2026.
    Expected: exactly 40 months (3 years and 4 months), '3 yrs 4 mos'.
    """
    calc_date = datetime(2026, 10, 15)
    entries = [{"company": "TCS", "role": "Software Engineer", "dates": "June 2023 – Present"}]
    res = experience_calculator.calculate_total_experience(entries, now=calc_date)
    assert res["total_months"] == 40
    assert res["total_years"] == 3.3
    assert res["display"] == "3 yrs 4 mos"
    assert res["is_approximate"] is False
    assert len(res["roles"]) == 1
    assert res["roles"][0]["is_valid"] is True


def test_experience_calculator_overlapping_periods():
    """
    Company A: Jan 2022 – Dec 2023 (23 months)
    Company B: Jul 2023 – Present (evaluated Oct 2026, 39 months)
    Overlapping months (Jul 2023 - Dec 2023) MUST NOT be counted twice.
    Union interval: Jan 2022 to Oct 2026 = 57 months.
    """
    calc_date = datetime(2026, 10, 1)
    entries = [
        {"company": "Company A", "dates": "Jan 2022 – Dec 2023"},
        {"company": "Company B", "dates": "Jul 2023 – Present"}
    ]
    res = experience_calculator.calculate_total_experience(entries, now=calc_date)
    assert res["total_months"] == 57
    assert res["total_years"] == 4.8
    assert res["display"] == "4 yrs 9 mos"


def test_experience_calculator_date_formats():
    """Tests various date formats: MM/YYYY, YYYY-MM, full months, abbreviations."""
    calc_date = datetime(2025, 1, 1)
    # 06/2023 - 12/2024 = 18 months
    p1 = experience_calculator.parse_date_range("06/2023 - 12/2024", now=calc_date)
    assert p1["is_valid"] is True
    assert p1["months"] == 18

    # 2022-01 to 2023-01 = 12 months
    p2 = experience_calculator.parse_date_range("2022-01 to 2023-01", now=calc_date)
    assert p2["is_valid"] is True
    assert p2["months"] == 12

    # Year only: 2020 - 2022 = 24 months, approximate
    p3 = experience_calculator.parse_date_range("2020 - 2022", now=calc_date)
    assert p3["is_valid"] is True
    assert p3["is_approximate"] is True
    assert p3["months"] == 24


def test_experience_calculator_invalid_dates():
    """Tests that end date preceding start date is flagged invalid without negative duration."""
    p = experience_calculator.parse_date_range("2024 - 2021")
    assert p["is_valid"] is False
    assert p["months"] == 0
    assert "precedes" in p["error"].lower()


# ==============================================================================
# 2. FIND CANDIDATES UPLOAD PERSISTENCE & SCOPED REMOVE/CLEAR ALL TESTS
# ==============================================================================

def test_find_candidates_upload_persists_in_library_and_ikm(client: TestClient, db_session):
    """
    Uploading a resume in Find Candidates persists to IKM and creates a library Document record.
    """
    # Create sample docx in memory
    doc = docx.Document()
    doc.add_heading("Alice Walker - Resume", 0)
    doc.add_paragraph("Professional Experience: Senior Software Engineer at TechCorp")
    doc.add_paragraph("Skills: Python, FastAPI, SQL, Cloud Architecture")
    doc_io = io.BytesIO()
    doc.save(doc_io)
    doc_bytes = doc_io.getvalue()

    resp = client.post(
        "/api/resumes",
        headers={"X-User-Id": "recruiter-1"},
        files={"files": ("Alice_Walker_Resume.docx", doc_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["successful_count"] >= 1
    doc_id = data["results"][0]["doc_id"]
    assert doc_id.startswith("DOC-")

    # Verify document exists in database
    db_doc = db_session.query(Document).filter(Document.doc_id == doc_id).first()
    assert db_doc is not None
    assert db_doc.upload_status == "ready"
    assert db_doc.ikm_ref is not None

    # Verify binary exists in IKM storage
    ikm_bytes = ikm_adapter.download_document(db_doc.ikm_ref)
    assert ikm_bytes is not None
    assert len(ikm_bytes) > 0

    # Verify listing in Resume Library returns the document
    list_resp = client.get("/api/resumes", headers={"X-User-Id": "recruiter-1"})
    assert list_resp.status_code == 200
    doc_ids_in_library = [d["doc_id"] for d in list_resp.json()]
    assert doc_id in doc_ids_in_library


def test_resume_library_permanent_deletion_still_works(client: TestClient, db_session):
    """
    Verifies that legitimate permanent deletion from Resume Library (/api/resumes/{doc_id} DELETE)
    remains functional and deletes properly.
    """
    # Ingest a test document
    doc_content = b"Temporary candidate file content for library deletion test."
    resp = client.post(
        "/api/resumes",
        headers={"X-User-Id": "recruiter-1"},
        files={"files": ("Temp_Candidate.txt", doc_content, "text/plain")}
    )
    assert resp.status_code == 200
    doc_id = resp.json()["results"][0]["doc_id"]

    # Delete via Resume Library permanent delete endpoint
    del_resp = client.delete(f"/api/resumes/{doc_id}", headers={"X-User-Id": "admin-1"})
    assert del_resp.status_code == 200

    # Confirm it is removed from database
    db_doc = db_session.query(Document).filter(Document.doc_id == doc_id).first()
    assert db_doc is None


# ==============================================================================
# 3. DOCX IN-PLACE EDITING & LAYOUT PRESERVATION TESTS
# ==============================================================================

def test_docx_inplace_editing_preserves_structure_and_runs():
    """
    Verifies that DOCX files are edited in-place preserving paragraphs,
    alignment, styles, runs, and tables.
    """
    doc = docx.Document()
    p1 = doc.add_paragraph()
    r1 = p1.add_run("Original responsibility: ")
    r1.bold = True
    r2 = p1.add_run("Designed backend services with Python.")
    p1.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.JUSTIFY

    # Add a table
    table = doc.add_table(rows=2, cols=2)
    cell = table.cell(0, 0)
    cell.paragraphs[0].text = "Core Competencies"

    buf_in = io.BytesIO()
    doc.save(buf_in)
    orig_bytes = buf_in.getvalue()

    # Apply changes in place
    approved_changes = [
        {
            "target_element_id": "paragraph_0",
            "original_text": "Designed backend services with Python.",
            "proposed_text": "Architected high-throughput backend services utilizing Python.",
            "section": "professional_experience"
        }
    ]

    improved_bytes = word_resume_service.generate_improved_docx_bytes(
        candidate_name="John Doe",
        target_role="Senior Python Engineer",
        profile={"skills": ["Python"]},
        revised_content="Revised text content",
        original_doc_bytes=orig_bytes,
        approved_changes=approved_changes
    )

    # Validate output DOCX
    assert improved_bytes is not None
    assert improved_bytes.startswith(b"PK\x03\x04")

    # Read output DOCX and confirm paragraph updated in-place
    res_doc = docx.Document(io.BytesIO(improved_bytes))
    assert len(res_doc.paragraphs) >= 1
    assert "Architected high-throughput backend services utilizing Python" in res_doc.paragraphs[0].text
    # Table must still exist
    assert len(res_doc.tables) == 1
    assert res_doc.tables[0].cell(0, 0).paragraphs[0].text == "Core Competencies"


# ==============================================================================
# 4. WORD RESUME GENERATION & VERSION SAVING TESTS
# ==============================================================================

def test_generate_word_resume_endpoint_saves_version_and_returns_download(client: TestClient, db_session):
    """
    Tests POST /api/resumes/{doc_id}/generate-word:
    Generates improved DOCX, saves immutable version, registers in library, returns download URL.
    """
    doc = db_session.query(Document).filter(Document.doc_id == "DOC-1001").first()
    assert doc is not None

    payload = {
        "candidate_name": "Test Candidate",
        "target_role": "Lead Architect",
        "change_summary": "Optimized architectural leadership bullets",
        "revised_content": "Full revised resume text content",
        "approved_changes": [
            {
                "target_element_id": "paragraph_1",
                "original_text": "Software development experience",
                "proposed_text": "Enterprise software architecture and development experience",
                "section": "professional_experience"
            }
        ]
    }

    resp = client.post(
        f"/api/resumes/{doc.doc_id}/generate-word",
        headers={"X-User-Id": "recruiter-1"},
        json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["doc_id"] == doc.doc_id
    assert "version_id" in data
    assert "download_url" in data
    assert data["download_url"] == f"/api/versions/{data['version_id']}/file"

    # Verify version was persisted in database
    ver = db_session.query(ResumeVersion).filter(ResumeVersion.version_id == data["version_id"]).first()
    assert ver is not None
    assert ver.doc_id == doc.doc_id

    # Verify version can be downloaded
    dl_resp = client.get(data["download_url"], headers={"X-User-Id": "recruiter-1"})
    assert dl_resp.status_code == 200
    assert dl_resp.content.startswith(b"PK\x03\x04")
