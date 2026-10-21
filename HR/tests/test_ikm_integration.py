import pytest
from app.integrations.ikm_adapter import ikm_adapter, HttpIKMAdapter, LocalIKMAdapter
from app.config import settings

def test_ikm_adapter_is_http_adapter():
    """Verifies that HttpIKMAdapter is active when IKM is enabled with URL."""
    assert isinstance(ikm_adapter, HttpIKMAdapter)
    assert ikm_adapter.base_url == "http://16.113.145.53:8088"
    assert ikm_adapter.username == "resume-screening"

def test_ikm_health_status_live_probe():
    """Verifies that the live server at 16.113.145.53:8088 is probed accurately."""
    status = ikm_adapter.get_health_status()
    assert "online" in status
    assert "authenticated" in status
    assert "service" in status
    # The real server is currently responding on 16.113.145.53:8088
    if status["online"]:
        assert status["service"] == "dms-service"
        assert status["prompt_guard"] is not None

def test_ikm_auth_graceful_credential_rejection():
    """Verifies that incorrect credentials do not crash the app, but record a clear message."""
    # Authenticate with current placeholder password
    success = ikm_adapter.authenticate(force=True)
    # Placeholder password returns 401 as expected
    assert success is False
    assert ikm_adapter._last_auth_error is not None
    assert "Invalid credentials" in ikm_adapter._last_auth_error or "401" in ikm_adapter._last_auth_error

def test_ikm_seamless_local_fallback_on_ingestion():
    """Verifies that ingestion and search fall back gracefully to local engine when unauthenticated."""
    # Ingest document
    res = ikm_adapter.ingest_document("TEST-DOC-1", "sample_data/resumes/john_doe.pdf")
    assert "ikm_ref" in res
    assert res["status"] in ("ready", "processing")

    # Search
    search_res = ikm_adapter.search("Python FastAPI", top_k=5)
    assert isinstance(search_res, list)

def test_ikm_api_status(client):
    """Verifies GET /api/ikm/status."""
    resp = client.get("/api/ikm/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "online" in data
    assert "authenticated" in data
    assert "base_url" in data

def test_ikm_api_test_auth(client):
    """Verifies POST /api/ikm/test-auth."""
    resp = client.post("/api/ikm/test-auth", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "success" in data
    assert "message" in data

def test_ikm_api_retrieve(client):
    """Verifies POST /api/ikm/retrieve."""
    resp = client.post("/api/ikm/retrieve", json={"query": "Python and PostgreSQL", "top_k": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "Python and PostgreSQL"
    assert "results" in data

def test_ikm_api_template_fallback(client):
    """Verifies GET /api/ikm/resumes/{doc_id}/template returns structured profile."""
    # First get an existing document ID from list
    res = client.get("/api/resumes")
    assert res.status_code == 200
    doc_list = res.json()
    if doc_list:
        doc_id = doc_list[0]["doc_id"]
        tpl_resp = client.get(f"/api/ikm/resumes/{doc_id}/template")
        assert tpl_resp.status_code == 200
        tpl_data = tpl_resp.json()
        assert "document_id" in tpl_data

def test_ikm_mask_sensitive_data():
    """Verifies that IKM redaction engine masks sensitive candidate details with standard tokens."""
    sample_text = (
        "Alice Walker\n"
        "Email: alice.walker@example.com | Phone: +1 555-234-5678\n"
        "Location: San Francisco, CA\n\n"
        "Professional Summary\n"
        "Experienced software engineer with 5 years building distributed systems."
    )
    masked_text, pii = ikm_adapter.mask_sensitive_data(sample_text)
    assert "[CANDIDATE_EMAIL]" in masked_text
    assert "alice.walker@example.com" not in masked_text
    assert "[CANDIDATE_PHONE]" in masked_text
    assert "+1 555-234-5678" not in masked_text
    assert pii.get("name") == "Alice Walker"
    assert pii.get("email") == "alice.walker@example.com"

def test_ikm_extract_resume_template():
    """Verifies that IKM scrapes and parses a candidate resume into a standardized JSON template."""
    sample_text = (
        "Bob Smith\n"
        "Email: bob.smith@example.com | Phone: +1 415-888-9999\n"
        "Location: Seattle, WA\n\n"
        "Professional Summary\n"
        "Senior Cloud Engineer specializing in AWS, Docker, and Kubernetes.\n\n"
        "Technical Skills\n"
        "Python, Docker, Kubernetes, AWS, PostgreSQL, Redis\n\n"
        "Experience\n"
        "Backend Developer at Tech Corp (2021 - 2024)\n"
        "- Engineered microservices handling 10k req/sec."
    )
    tpl = ikm_adapter.extract_resume_template("DOC-TEST-1", sample_text)
    assert tpl["doc_id"] == "DOC-TEST-1"
    assert "contact_block" in tpl
    assert tpl["contact_block"]["name"] == "Bob Smith"
    assert tpl["contact_block"]["email"] == "bob.smith@example.com"
    assert "skills" in tpl
    assert any(s.lower() == "python" for s in tpl["skills"])
    assert "experience" in tpl
    assert len(tpl["experience"]) > 0

def test_ikm_improve_resume_from_template():
    """Verifies that resume improvement uses the IKM JSON template with targeted skill modifications."""
    from app.integrations.grok_adapter import grok_adapter
    
    template = {
        "doc_id": "DOC-999",
        "contact_block": {
            "name": "Jane Doe",
            "email": "jane.doe@example.com",
            "phone": "+1 555-000-1111",
            "location": "New York, NY"
        },
        "target_role": "Backend Engineer",
        "summary": "Experienced engineer with skills in Python and databases.",
        "skills": ["Python", "SQL", "Git"],
        "experience": [
            {
                "role": "Software Developer",
                "company": "Acme Corp",
                "dates": "2022 - Present",
                "bullets": ["Developed APIs and integrated databases."]
            }
        ],
        "projects": [
            {
                "name": "Cloud Microservices",
                "technologies": ["Python"],
                "bullets": ["Engineered core backend endpoints."]
            }
        ],
        "education": [{"degree": "B.Tech", "field": "Computer Science", "institution": "State University", "year": "2022"}]
    }

    result = grok_adapter.improve_resume_from_ikm_template(
        template_json=template,
        candidate_name="Jane Doe",
        target_role="Senior Cloud Platform Engineer",
        required_skills=["Kubernetes", "AWS", "FastAPI"],
        gaps=[{"requirement": "Kubernetes", "recommendation": "Add orchestrations"}],
        matched=[{"requirement": "Python"}],
        personal_details={"name": "Jane Doe", "email": "jane.doe@example.com"}
    )

    assert "improved_resume_text" in result
    assert "modified_template" in result
    mod_tpl = result["modified_template"]
    assert "Kubernetes" in mod_tpl["skills"]
    assert "AWS" in mod_tpl["skills"]
    assert mod_tpl["contact_block"]["name"] == "Jane Doe"
    assert "Senior Cloud Platform Engineer" in result["improved_resume_text"]

def test_api_mask_sensitive_data(client):
    """Verifies POST /api/ikm/mask-sensitive-data endpoint."""
    resp = client.post("/api/ikm/mask-sensitive-data", json={
        "text": "Charlie Brown\nEmail: charlie@peanuts.com\nPhone: +1 555-432-1098"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "masked_text" in data
    assert "[CANDIDATE_EMAIL]" in data["masked_text"]
    assert "charlie@peanuts.com" not in data["masked_text"]

def test_api_identify_skills(client):
    """Verifies POST /api/ikm/identify-skills endpoint."""
    resp = client.post("/api/ikm/identify-skills", json={
        "text": "Experienced building FastAPI backends with PostgreSQL, Docker, and Redis."
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" in data
    assert any(s in data["skills"] for s in ["FastAPI", "PostgreSQL", "Docker", "Redis"])

def test_api_get_resume_ikm_template(client):
    """Verifies GET /api/ikm/resumes/{doc_id}/ikm-template endpoint."""
    res = client.get("/api/resumes")
    assert res.status_code == 200
    doc_list = res.json()
    if doc_list:
        doc_id = doc_list[0]["doc_id"]
        tpl_resp = client.get(f"/api/ikm/resumes/{doc_id}/ikm-template")
        assert tpl_resp.status_code == 200
        tpl_data = tpl_resp.json()
        assert tpl_data["doc_id"] == doc_id
        assert "ikm_template" in tpl_data
        assert "contact_block" in tpl_data["ikm_template"]

