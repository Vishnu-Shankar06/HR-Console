import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.integrations.ikm_adapter import ikm_adapter
from app.models.database import SessionLocal
from app.services.ikm_sync_service import sync_ikm_with_database

@pytest.fixture(autouse=True)
def clean_test_environment():
    """Ensure a clean repository and database state before and after each test."""
    repo_id = ikm_adapter.repository_id
    if ikm_adapter.authenticate():
        docs = ikm_adapter.list_documents(repository_id=repo_id, force=True)
        for d in docs:
            ikm_adapter.delete_document(d.get("document_id"))
    db = SessionLocal()
    sync_ikm_with_database(db=db, force=True)
    db.close()
    yield
    if ikm_adapter.authenticate():
        docs = ikm_adapter.list_documents(repository_id=repo_id, force=True)
        for d in docs:
            ikm_adapter.delete_document(d.get("document_id"))
    db = SessionLocal()
    sync_ikm_with_database(db=db, force=True)
    db.close()

def test_ikm_upload_reflects_in_ikm():
    client = TestClient(app)
    repo_id = ikm_adapter.repository_id

    # 1. Upload via application
    content = b"Candidate Resume: John Python Developer. Experience: 4 years FastAPI."
    resp = client.post(
        "/api/resumes",
        files={"files": ("john_doe_sync.txt", io.BytesIO(content), "text/plain")}
    )
    assert resp.status_code == 200
    res_data = resp.json()["results"][0]
    assert res_data["status"] == "ready"
    doc_id = res_data["doc_id"]

    # 2. Check IKM has document in target repository
    ikm_docs = ikm_adapter.list_documents(repository_id=repo_id, force=True)
    assert len(ikm_docs) == 1
    assert "john_doe_sync" in ikm_docs[0].get("original_file_name", "")

    # Cleanup
    client.delete(f"/api/resumes/{doc_id}")

def test_app_delete_reflects_in_ikm():
    client = TestClient(app)
    repo_id = ikm_adapter.repository_id

    # 1. Upload
    content = b"Candidate Resume: Alice Cloud Engineer. Experience: 6 years AWS Docker."
    resp = client.post(
        "/api/resumes",
        files={"files": ("alice_cloud_sync.txt", io.BytesIO(content), "text/plain")}
    )
    assert resp.status_code == 200
    doc_id = resp.json()["results"][0]["doc_id"]

    # Verify present in IKM
    assert len(ikm_adapter.list_documents(repository_id=repo_id, force=True)) == 1

    # 2. Delete via application
    del_resp = client.delete(f"/api/resumes/{doc_id}")
    assert del_resp.status_code == 200

    # 3. Verify removed from IKM
    ikm_docs = ikm_adapter.list_documents(repository_id=repo_id, force=True)
    assert len(ikm_docs) == 0

def test_ikm_delete_reflects_inside_application():
    client = TestClient(app)
    repo_id = ikm_adapter.repository_id

    # 1. Upload via application
    content = b"Candidate Resume: Bob Security Engineer. Experience: 5 years CISSP."
    resp = client.post(
        "/api/resumes",
        files={"files": ("bob_sec_sync.txt", io.BytesIO(content), "text/plain")}
    )
    assert resp.status_code == 200
    doc_id = resp.json()["results"][0]["doc_id"]

    # Get IKM document ID
    ikm_docs = ikm_adapter.list_documents(repository_id=repo_id, force=True)
    assert len(ikm_docs) == 1
    ikm_doc_id = ikm_docs[0]["document_id"]

    # 2. Delete directly from IKM
    deleted = ikm_adapter.delete_document(ikm_doc_id)
    assert deleted is True
    assert len(ikm_adapter.list_documents(repository_id=repo_id, force=True)) == 0

    # 3. Application list endpoint should reflect the deletion
    list_resp = client.get("/api/resumes")
    assert list_resp.status_code == 200
    app_doc_ids = [d["doc_id"] for d in list_resp.json()]
    assert doc_id not in app_doc_ids

