import pytest
from fastapi.testclient import TestClient

def test_resume_preview_text_and_docx(client: TestClient):
    # Test preview for DOC-1001
    resp = client.get("/api/resumes/DOC-1001/preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["doc_id"] == "DOC-1001"
    assert "pages" in data
    assert len(data["pages"]) >= 1
    assert data["total_pages"] >= 1
    assert "Arun Kumar" in data["pages"][0] or "python" in data["pages"][0].lower()

    # Test preview for DOC-1002 (DOCX)
    resp_docx = client.get("/api/resumes/DOC-1002/preview")
    assert resp_docx.status_code == 200
    data_docx = resp_docx.json()
    assert data_docx["success"] is True
    assert data_docx["doc_id"] == "DOC-1002"
    assert len(data_docx["pages"]) >= 1
    assert "Priya Sharma" in data_docx["pages"][0] or "doc-cand-name" in data_docx["pages"][0]

def test_resume_preview_multipage_structure(client: TestClient):
    resp = client.get("/api/resumes/DOC-1001/preview")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["pages"], list)
    assert data["total_pages"] == len(data["pages"])
    # First page should contain formatted HTML
    first_page = data["pages"][0]
    assert "<" in first_page and ">" in first_page

def test_resume_stream_inline(client: TestClient):
    resp = client.get("/api/resumes/DOC-1001/stream")
    assert resp.status_code == 200
    # Content-Disposition must NOT be attachment
    disposition = resp.headers.get("content-disposition", "")
    assert "attachment" not in disposition.lower()

def test_resume_preview_not_found(client: TestClient):
    resp = client.get("/api/resumes/NON-EXISTENT-DOC/preview")
    assert resp.status_code == 404
