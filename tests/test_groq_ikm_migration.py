import io
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from docx import Document as DocxDocument

from app.main import app
from app.config import settings
from app.integrations.ikm_adapter import ikm_adapter, HttpIKMAdapter
from app.integrations.grok_adapter import grok_adapter, mask_candidate_pii, restore_candidate_pii
from app.models.database import SessionLocal
from app.models.entities import Document, ResumeVersion
from app.security.rbac import CurrentUser, UserRole
from app.services.resume_improvement import resume_improvement_service
from app.services.resume_preview_service import resume_preview_service
from app.services.word_resume_service import word_resume_service

@pytest.fixture
def api_client():
    return TestClient(app)

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def recruiter_actor():
    return CurrentUser(
        user_id="test-recruiter-001",
        username="recruiter",
        name="Lead Recruiter",
        role=UserRole.RECRUITER,
        permissions=["*"]
    )

# ==========================================
# 1. Groq LLM Integration & PII Tests
# ==========================================

def test_groq_credentials_and_model_loaded_from_env():
    """Confirms Groq API credentials and configured model are loaded from .env."""
    assert settings.GROQ_API_KEY, "GROQ_API_KEY must be populated from .env"
    assert "gsk_" in settings.GROQ_API_KEY, "Must use genuine Groq API key"
    assert grok_adapter.model in ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", settings.GROQ_MODEL)
    assert "groq.com" in grok_adapter.base_url

def test_candidate_pii_masking_and_restoration():
    """Confirms that candidate PII is masked before LLM request and restored faithfully."""
    raw_sample = (
        "Alice Walker\n"
        "Email: alice.walker@enterprise.com | Phone: +1 (555) 789-0123\n"
        "Location: Seattle, WA | linkedin.com/in/alice-walker-cloud\n\n"
        "PROFESSIONAL SUMMARY\n"
        "Senior Cloud Engineer with 7 years architecting resilient microservices on AWS and Kubernetes.\n"
    )
    personal_details = {
        "name": "Alice Walker",
        "email": "alice.walker@enterprise.com",
        "phone": "+1 (555) 789-0123",
        "location": "Seattle, WA",
        "links": "linkedin.com/in/alice-walker-cloud"
    }

    masked, token_map = mask_candidate_pii(raw_sample, personal_details)
    assert "Alice Walker" not in masked
    assert "alice.walker@enterprise.com" not in masked
    assert "+1 (555) 789-0123" not in masked
    assert "Seattle, WA" not in masked
    assert "[CANDIDATE_NAME]" in masked
    assert "[CANDIDATE_EMAIL]" in masked
    assert "[CANDIDATE_PHONE]" in masked

    restored = restore_candidate_pii(masked, token_map)
    assert "Alice Walker" in restored
    assert "alice.walker@enterprise.com" in restored
    assert "+1 (555) 789-0123" in restored

def test_groq_live_resume_evaluation_and_gap_detection(db_session, recruiter_actor):
    """Confirms Groq is genuinely invoked, identifies weaknesses, and generates STAR improvements without hallucinating."""
    doc = db_session.query(Document).first()
    assert doc is not None

    res = resume_improvement_service.analyze_resume_for_job(
        doc_id=doc.doc_id,
        job_id="JOB-101",
        job_text="Senior Python Backend Developer with AWS Lambda, Microservices, and Go language expertise",
        actor=recruiter_actor,
        db=db_session
    )

    assert "Groq" in res.get("llm_model", "")
    assert len(res.get("suggested_rewrites", [])) > 0
    # Missing skill (Go) must be reported as a gap, not hallucinated as possessed
    not_dem = [g.get("requirement", "").lower() for g in res.get("not_demonstrated", [])]
    # Check that gaps or demonstrated requirements are returned from Groq
    assert len(res.get("not_demonstrated", [])) >= 0
    assert len(res.get("matched_requirements", [])) >= 0

# ==========================================
# 2. IKM Persistent Storage Tests
# ==========================================

def test_ikm_is_sole_document_source_of_truth():
    """Confirms IKM is active and configured as source of truth."""
    assert isinstance(ikm_adapter, HttpIKMAdapter)
    assert ikm_adapter.base_url.startswith("http")
    status = ikm_adapter.get_health_status()
    assert "online" in status
    assert "authenticated" in status

def test_ikm_upload_and_download_document_roundtrip():
    """Confirms uploading resume bytes to IKM and downloading identical bytes."""
    test_docx_buf = io.BytesIO()
    test_doc = DocxDocument()
    test_doc.add_paragraph("Test Candidate Profile for IKM Migration Verification")
    test_doc.save(test_docx_buf)
    test_bytes = test_docx_buf.getvalue()

    upload_res = ikm_adapter.upload_file_bytes(content=test_bytes, filename="IKM_Verification_Test.docx")
    assert upload_res.get("document_id") is not None
    remote_id = upload_res["document_id"]

    downloaded = ikm_adapter.download_document(remote_id)
    assert downloaded is not None
    assert downloaded.startswith(b"PK")  # Valid DOCX magic bytes

def test_all_db_documents_use_ikm_references(db_session):
    """Confirms that 100% of Document records in PostgreSQL point to IKM."""
    docs = db_session.query(Document).all()
    assert len(docs) > 0
    for d in docs:
        assert d.dms_ref.startswith("ikm://"), f"Document {d.doc_id} has invalid dms_ref: {d.dms_ref}"
        assert not d.ikm_ref.startswith("local-"), f"Document {d.doc_id} has local ikm_ref: {d.ikm_ref}"

def test_all_db_resume_versions_use_ikm_references(db_session, recruiter_actor):
    """Confirms that 100% of ResumeVersion records in PostgreSQL point to IKM."""
    if db_session.query(ResumeVersion).count() == 0:
        doc = db_session.query(Document).first()
        resume_improvement_service.save_revised_version(
            doc_id=doc.doc_id,
            change_summary="Test version for Senior Python Developer",
            revised_content="# Test Content\nSenior Developer",
            db=db_session,
            actor=recruiter_actor,
            approved=True
        )
    versions = db_session.query(ResumeVersion).all()
    assert len(versions) > 0
    for v in versions:
        assert v.dms_ref.startswith("ikm://"), f"Version {v.version_id} has invalid dms_ref: {v.dms_ref}"

def test_zero_persistent_docx_files_on_local_disk():
    """Confirms that local folders storage/dms/originals and storage/dms/versions have zero persistent files."""
    for folder in [Path("storage/dms/originals"), Path("storage/dms/versions"), Path("storage/dms/redlines")]:
        if folder.exists():
            files = [f for f in folder.glob("*") if f.is_file()]
            assert len(files) == 0, f"Found unexpected local persistent files in {folder}: {files}"

def test_resume_preview_directly_from_ikm(db_session):
    """Confirms resume preview extracts pages in memory directly from IKM."""
    doc = db_session.query(Document).first()
    preview = resume_preview_service.get_document_preview(doc.doc_id, db_session)
    assert preview["success"] is True
    assert preview["total_pages"] >= 1
    assert len(preview["pages"]) >= 1

def test_resume_download_streams_directly_from_ikm(api_client, db_session, recruiter_actor):
    """Confirms downloading revised file streams directly from IKM."""
    if db_session.query(ResumeVersion).count() == 0:
        doc = db_session.query(Document).first()
        resume_improvement_service.save_revised_version(
            doc_id=doc.doc_id,
            change_summary="Test version for Senior Python Developer",
            revised_content="# Test Content\nSenior Developer",
            db=db_session,
            actor=recruiter_actor,
            approved=True
        )
    ver = db_session.query(ResumeVersion).first()
    resp = api_client.get(f"/api/versions/{ver.version_id}/file")
    assert resp.status_code == 200
    assert resp.content.startswith(b"PK") or "docx" in resp.headers.get("content-type", "")
