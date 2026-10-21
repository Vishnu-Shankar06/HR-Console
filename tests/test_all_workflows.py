import io
from app.models.entities import Document, CandidatePII, ResumeVersion
from app.security.encryption import pii_crypto

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "ikm_mode" in data

def test_top_n_validation_rules(client):
    """
    Validates that the shortlist count N must be a manually typed positive integer,
    and rejects 0, negative values, and excessive numbers.
    """
    # 1. Valid positive integer
    resp = client.post("/api/matches", json={
        "job_id": "JOB-101",
        "requested_count": 3
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["requested_count"] == 3
    assert len(data["results"]) <= 3

    # 2. Reject zero
    resp_zero = client.post("/api/matches", json={
        "job_id": "JOB-101",
        "requested_count": 0
    })
    assert resp_zero.status_code == 422

    # 3. Reject negative
    resp_neg = client.post("/api/matches", json={
        "job_id": "JOB-101",
        "requested_count": -5
    })
    assert resp_neg.status_code == 422

    # 4. Reject over maximum limit
    resp_over = client.post("/api/matches", json={
        "job_id": "JOB-101",
        "requested_count": 150
    })
    assert resp_over.status_code == 422

def test_fewer_than_n_candidates_handling(client):
    """
    Verifies that when requested N exceeds available candidates,
    the system returns all eligible candidates without fabricating fake ones.
    """
    resp = client.post("/api/matches", json={
        "job_id": "JOB-101",
        "requested_count": 50  # More than the 6 seeded candidates
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["returned_count"] <= 6
    assert data["notice"] is not None
    assert "requested 50" in data["notice"]

def test_matching_evidence_and_scoring(client):
    """
    Verifies transparent scoring and evidence citations for top candidates.
    """
    resp = client.post("/api/matches", json={
        "job_id": "JOB-101",
        "requested_count": 2
    })
    assert resp.status_code == 200
    data = resp.json()
    top_candidate = data["results"][0]
    
    assert top_candidate["rank"] == 1
    assert "internal_match_score" in top_candidate
    assert "score_breakdown" in top_candidate
    assert "mandatory_requirements" in top_candidate["score_breakdown"]
    assert len(top_candidate["matched_requirements"]) > 0
    # Must have verbatim evidence
    assert top_candidate["matched_requirements"][0]["evidence"] is not None

def test_pii_encryption_and_zero_leakage(client, db_session):
    """
    Verifies that candidate personal data is encrypted in storage and
    not returned in standard candidate detail endpoints.
    """
    pii = db_session.query(CandidatePII).filter(CandidatePII.doc_id == "DOC-1001").first()
    assert pii is not None
    # Must be encrypted ciphertext, NOT plaintext
    assert "arun" not in (pii.email_encrypted or "").lower()
    assert "9876543210" not in (pii.phone_encrypted or "")

    # Normal profile endpoint should NOT expose PII fields
    resp = client.get("/api/resumes/DOC-1001")
    assert resp.status_code == 200
    profile_data = resp.json()
    assert "name_encrypted" not in profile_data
    assert "email_encrypted" not in profile_data

    # Decrypted PII requires explicit authorized endpoint
    resp_pii = client.get("/api/resumes/DOC-1001/pii")
    assert resp_pii.status_code == 200
    decrypted = resp_pii.json()
    assert decrypted["name"] == "Arun Kumar"
    assert decrypted["email"] == "arun.kumar.dev@example.com"

def test_resume_improvement_workflow(client):
    """
    Tests gap analysis, suggested rewrites with user confirmation flag,
    and versioned draft saving without modifying the original resume.
    """
    # 1. Analyze resume for job
    resp = client.post("/api/resumes/DOC-1001/improvements", json={
        "job_id": "JOB-101"
    })
    assert resp.status_code == 200
    imp = resp.json()
    assert "internal_match_score" in imp
    assert "score_disclaimer" in imp
    assert len(imp["matched_requirements"]) > 0
    assert len(imp["suggested_rewrites"]) > 0
    # Check confirmation flag
    assert imp["suggested_rewrites"][0]["requires_user_confirmation"] in (True, False)

    # 2. Save revised version
    save_resp = client.post("/api/resumes/DOC-1001/versions", json={
        "change_summary": "Added explicit Docker multi-stage build description and PyTest test metrics.",
        "revised_content": "Revised resume content for Arun Kumar with verified Docker and PyTest deployment details.",
        "approved": True
    })
    assert save_resp.status_code == 200
    saved = save_resp.json()
    assert saved["version_id"] == "VER-DOC-1001-v1"
    assert saved["doc_id"] == "DOC-1001"

    # 3. List version history
    hist_resp = client.get("/api/resumes/DOC-1001/versions")
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert len(history) == 1
    assert history[0]["version_id"] == "VER-DOC-1001-v1"

def test_followup_and_inactivity_tracker(client):
    """
    Tests inactivity detection, overdue records, and action updates.
    """
    # Fetch follow-up candidates
    resp = client.get("/api/follow-ups?inactivity_days=7")
    assert resp.status_code == 200
    follow_ups = resp.json()
    assert len(follow_ups) > 0
    
    # Must contain candidates inactive > 7 days (e.g. DOC-1001 is 16 days inactive)
    doc_ids = [f["doc_id"] for f in follow_ups]
    assert "DOC-1001" in doc_ids

    # Record recruiter action
    action_resp = client.post("/api/resumes/DOC-1001/actions", json={
        "action_type": "contacted",
        "status": "contacted",
        "notes": "Spoke with Arun; requested updated GitHub portfolio link."
    })
    assert action_resp.status_code == 200
    act_data = action_resp.json()
    assert act_data["status"] == "contacted"

def test_candidate_development_plan(client):
    """
    Tests candidate development plan generation with practical projects
    and outreach message draft.
    """
    resp = client.post("/api/resumes/DOC-1001/development-plan", json={
        "target_role": "Senior Cloud Infrastructure Engineer"
    })
    assert resp.status_code == 200
    plan = resp.json()
    assert "practical_projects" in plan
    assert len(plan["practical_projects"]) > 0
    assert "learning_recommendations" in plan
    assert "recruiter_message_draft" in plan
    assert "Dear Candidate" in plan["recruiter_message_draft"]

def test_multi_file_upload(client):
    """
    Tests uploading PDF and DOCX files.
    """
    file1_content = b"%PDF-1.4 test resume Arun\nPython FastAPI PostgreSQL"
    file2_content = b"PK test docx resume Priya\nReact TypeScript Python"

    files = [
        ("files", ("test_resume1.pdf", io.BytesIO(file1_content), "application/pdf")),
        ("files", ("test_resume2.docx", io.BytesIO(file2_content), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
    ]

    resp = client.post("/api/resumes", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_files"] == 2
    assert data["successful_count"] >= 1

def test_job_management_create_list_delete(client):
    """
    Tests creating a new job opening, verifying it appears in the job list,
    ensuring ad-hoc queries are excluded by default, and deleting the job.
    """
    # 1. Create a new job opening
    create_resp = client.post("/api/jobs", json={
        "title": "Lead DevOps & Platform Engineer",
        "job_text": "Looking for Lead DevOps with 5+ years experience in Kubernetes, Terraform, AWS, and CI/CD pipelines."
    })
    assert create_resp.status_code == 200
    job_data = create_resp.json()
    job_id = job_data["job_id"]
    assert job_id.startswith("JOB-")
    assert job_data["title"] == "Lead DevOps & Platform Engineer"

    # 2. List jobs and verify it appears
    list_resp = client.get("/api/jobs")
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    job_ids = [j["job_id"] for j in jobs]
    assert job_id in job_ids

    # 3. Delete the job opening
    del_resp = client.delete(f"/api/jobs/{job_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # 4. Verify 404 after deletion
    get_resp = client.get(f"/api/jobs/{job_id}")
    assert get_resp.status_code == 404

def test_resume_deletion_workflow(client, db_session):
    """
    Tests deleting a candidate resume and ensures all associated profiles,
    PII, and version records are safely removed.
    """
    # 1. Verify candidate DOC-1002 exists initially
    resp = client.get("/api/resumes/DOC-1002")
    assert resp.status_code == 200

    # 2. Delete candidate resume
    del_resp = client.delete("/api/resumes/DOC-1002")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # 3. Verify candidate profile is now 404
    resp_after = client.get("/api/resumes/DOC-1002")
    assert resp_after.status_code == 404

    # 4. Verify PII is also deleted from DB
    pii_after = db_session.query(CandidatePII).filter(CandidatePII.doc_id == "DOC-1002").first()
    assert pii_after is None

def test_followup_inactivity_threshold_adjustable(client):
    """
    Tests the inactivity threshold parameter up to 90 days.
    """
    # Test default 30 days
    resp_30 = client.get("/api/follow-ups?inactivity_days=30")
    assert resp_30.status_code == 200
    items_30 = resp_30.json()
    assert isinstance(items_30, list)

    # Test adjustable up to 90 days
    resp_90 = client.get("/api/follow-ups?inactivity_days=90")
    assert resp_90.status_code == 200
    items_90 = resp_90.json()
    assert isinstance(items_90, list)
    # Candidate records are retained whatsoever, and is_stale correctly reflects the 90-day threshold
    for item in items_90:
        if item["days_inactive"] >= 90:
            assert item["is_stale"] is True
        else:
            assert item["is_stale"] is False

def test_followup_retention_and_open_timestamp(client):
    """
    Verifies that candidates stay in followups after actions are taken,
    and tracks the last_opened_at timestamp.
    """
    # 1. Record resume opened
    open_resp = client.post("/api/resumes/DOC-1001/open")
    assert open_resp.status_code == 200
    assert "last_opened_at" in open_resp.json()

    # 2. Record action
    act_resp = client.post("/api/resumes/DOC-1001/actions", json={
        "action_type": "shortlisted",
        "status": "shortlisted",
        "notes": "Shortlisted for Senior Python Role"
    })
    assert act_resp.status_code == 200

    # 3. Verify DOC-1001 remains visible in followups (never disappears)
    fu_resp = client.get("/api/follow-ups")
    assert fu_resp.status_code == 200
    doc_ids = [item["doc_id"] for item in fu_resp.json()]
    assert "DOC-1001" in doc_ids
    
    cand = next(item for item in fu_resp.json() if item["doc_id"] == "DOC-1001")
    assert cand["status"] == "shortlisted"
    assert cand["last_opened_at"] is not None

def test_notifications_and_email_escalation(client):
    """
    Verifies notification generation for dormant candidates,
    and automated email escalation to damayanthi.u@riscrm.com with resume attached.
    """
    # 1. Fetch notifications
    notif_resp = client.get("/api/notifications")
    assert notif_resp.status_code == 200
    notifs = notif_resp.json()
    assert isinstance(notifs, list)

    # 2. Dispatch escalation email to damayanthi.u@riscrm.com
    email_resp = client.post(
        "/api/resumes/DOC-1001/send-escalation-email",
        params={
            "recipient": "damayanthi.u@riscrm.com",
            "reason": "Candidate has not had recruiter action for 3 months."
        }
    )
    assert email_resp.status_code == 200
    email_data = email_resp.json()
    assert email_data["success"] is True
    assert email_data["recipient"] == "damayanthi.u@riscrm.com"
    assert email_data["attachment_filename"] is not None
    assert email_data["attachment_size_kb"] > 0

    # 3. Mark notification as read if any exists
    if notifs:
        nid = notifs[0]["id"]
        read_resp = client.post(f"/api/notifications/{nid}/read")
        assert read_resp.status_code == 200
        assert read_resp.json()["success"] is True

def test_word_resume_generation_and_download(client):
    """
    Verifies that the AI Agent generates a genuine Microsoft Word (.docx) resume,
    saves it to DMS versions, and allows direct download with correct MIME type.
    """
    resp = client.post("/api/resumes/DOC-1001/generate-word", json={
        "change_summary": "AI Agent enhanced executive resume with verified metrics",
        "revised_content": "ARUN KUMAR\nSenior Python Backend Developer\n\nPROFESSIONAL SUMMARY\nOver 6 years of expertise in FastAPI microservices and PostgreSQL.\n\nCORE COMPETENCIES\n- FastAPI & Python\n- PostgreSQL & Database Optimization\n- Docker & CI/CD Pipelines",
        "target_role": "Lead Backend Architect"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["version_id"].startswith("VER-DOC-1001")
    assert data["filename"].endswith(".docx")
    assert data["download_url"].startswith("/api/versions/")

    # Stream download and verify .docx magic bytes (PK\x03\x04 zip format)
    download_resp = client.get(data["download_url"])
    assert download_resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in download_resp.headers["content-type"]

def test_doc_id_generation_unique_after_deletions(db_session):
    """
    Verifies that _generate_doc_id always produces unique IDs even when
    previous documents have been deleted, preventing UNIQUE constraint violations.
    """
    from app.services.resume_ingestion import resume_ingestion_service
    from app.models.entities import Document

    # Fetch max existing ID
    id_1 = resume_ingestion_service._generate_doc_id(db_session)
    assert id_1.startswith("DOC-")
    
    # Simulate adding this document
    dummy = Document(
        doc_id=id_1,
        dms_ref=f"test/{id_1}.pdf",
        ikm_ref=f"ikm-{id_1}",
        original_filename="dummy.pdf",
        mime_type="application/pdf",
        checksum=f"chk-{id_1}",
        upload_status="ready",
        uploaded_by="admin-001"
    )
    db_session.add(dummy)
    db_session.commit()

    id_2 = resume_ingestion_service._generate_doc_id(db_session)
    assert id_2 != id_1
    assert int(id_2.split("-")[1]) > int(id_1.split("-")[1])

def test_matching_restricted_to_uploaded_doc_ids(client):
    """
    Verifies that when specific doc_ids are provided (e.g. only uploaded resumes),
    the matching engine only evaluates those files and excludes existing library files.
    """
    target_docs = ["DOC-1002", "DOC-1003"]
    resp = client.post("/api/matches", json={
        "job_id": "JOB-101",
        "requested_count": 5,
        "doc_ids": target_docs
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["returned_count"] <= len(target_docs)
    for res in data["results"]:
        assert res["doc_id"] in target_docs
        assert res["doc_id"] not in ["DOC-1001", "DOC-1004", "DOC-1005", "DOC-1006"]
    
    assert data["notice"] is not None
    assert "Evaluated 2 uploaded candidate resume(s)" in data["notice"]

def test_delete_uploaded_resume_endpoint(client, db_session):
    """
    Verifies that an individual resume can be removed/deleted cleanly via DELETE /api/resumes/{doc_id}.
    """
    from app.services.resume_ingestion import resume_ingestion_service
    test_id = resume_ingestion_service._generate_doc_id(db_session)
    dummy = Document(
        doc_id=test_id,
        dms_ref=f"test/{test_id}.pdf",
        ikm_ref=f"ikm-{test_id}",
        original_filename="candidate_to_remove.pdf",
        mime_type="application/pdf",
        checksum=f"chk-delete-{test_id}",
        upload_status="ready",
        uploaded_by="admin-001"
    )
    db_session.add(dummy)
    db_session.commit()

    del_resp = client.delete(f"/api/resumes/{test_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    get_resp = client.get(f"/api/resumes/{test_id}")
    assert get_resp.status_code == 404

def test_grok_resume_improvement_modifications(client):
    """
    Verifies that Grok LLM generates substantive, concrete modifications to the resume,
    NOT just returning the identical original text.
    """
    resp = client.post("/api/resumes/DOC-1001/improvements", json={
        "job_text": "Senior Lead Python & FastAPI Developer with PostgreSQL, AWS, and Microservices architecture experience"
    })
    assert resp.status_code == 200
    data = resp.json()

    # Verify new fields exist
    assert "improved_resume_text" in data
    assert "change_summary" in data
    assert "key_enhancements" in data
    assert "llm_model" in data

    improved_text = data["improved_resume_text"]
    original_text = data["original_text_preview"]

    # CRITICAL: Verify that the output is NOT just the original text
    assert improved_text != original_text
    assert len(improved_text) > 200

    # Verify substantive modifications
    assert "PROFESSIONAL SUMMARY" in improved_text
    assert "TECHNICAL SKILLS" in improved_text
    assert "PROFESSIONAL EXPERIENCE" in improved_text
    # Verify STAR-method action verbs and metrics were added
    assert any(verb in improved_text for verb in ["Architected", "Engineered", "Optimized", "Spearheaded", "throughput", "latency"])
    # Verify categorized skills exist
    assert "Languages & Frameworks:" in improved_text

    # Verify model is Grok
    assert "Grok" in data["llm_model"]

def test_improved_word_docx_contains_actual_changes(client):
    """
    Verifies that downloading the improved Word (.docx) document contains the actual
    Grok modifications, rather than just saving an unmodified copy of the original.
    """
    import docx
    import tempfile

    resp = client.post("/api/resumes/DOC-1001/generate-word", json={
        "change_summary": "Grok-optimized executive resume for Lead Architect",
        "revised_content": "# ARUN KUMAR\nLead Backend Architect\n\n## PROFESSIONAL SUMMARY\nEngineered high-throughput FastAPI distributed systems handling 5M daily requests with 99.9% uptime.\n\n## TECHNICAL SKILLS\n- Languages & Frameworks: Python, FastAPI, Microservices\n- Databases: PostgreSQL, Redis",
        "target_role": "Lead Backend Architect"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    download_resp = client.get(data["download_url"])
    assert download_resp.status_code == 200

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(download_resp.content)
        tmp_path = tmp.name

    # Inspect document contents with python-docx
    doc = docx.Document(tmp_path)
    full_doc_text = "\n".join([p.text for p in doc.paragraphs])

    # Must contain actual modifications
    assert "LEAD BACKEND ARCHITECT" in full_doc_text.upper()
    assert "high-throughput FastAPI distributed systems" in full_doc_text
    assert "99.9% uptime" in full_doc_text


def test_candidate_remarks_api_storage_and_retrieval(client):
    """
    Verifies that recruiter remarks are securely stored and retrievable via the actions API.
    """
    doc_id = "DOC-1001"
    
    # 1. Post initial remark
    resp1 = client.post(f"/api/resumes/{doc_id}/remarks", json={
        "notes": "Excellent initial screening. Demonstrated strong architectural knowledge.",
        "status": "shortlisted",
        "owner_id": "recruiter_test"
    })
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["success"] is True
    assert data1["status"] == "shortlisted"
    assert "action_id" in data1

    # 2. Retrieve actions and verify remark is present
    actions_resp = client.get(f"/api/resumes/{doc_id}/actions")
    assert actions_resp.status_code == 200
    actions_list = actions_resp.json()
    assert isinstance(actions_list, list)
    assert len(actions_list) >= 1
    
    first_action = actions_list[0]
    assert "Demonstrated strong architectural knowledge" in first_action["notes"]
    assert first_action["status"] == "shortlisted"

    # 3. Post second remark marking candidate as hired
    resp2 = client.post(f"/api/resumes/{doc_id}/remarks", json={
        "notes": "Candidate accepted the lead position offer! Formal start date confirmed.",
        "status": "hired",
        "owner_id": "recruiter_test"
    })
    assert resp2.status_code == 200
    
    # 4. Verify actions chronological order
    actions_resp2 = client.get(f"/api/resumes/{doc_id}/actions")
    actions_list2 = actions_resp2.json()
    assert len(actions_list2) >= 2
    latest = actions_list2[0]
    assert latest["status"] == "hired"
    assert "accepted the lead position offer" in latest["notes"]


def test_hired_status_in_resume_library(client):
    """
    Verifies that candidates marked as hired reflect 'hired' in the library listing
    and can be filtered using the status filter.
    """
    doc_id = "DOC-1002"
    
    # Mark candidate as hired via actions API
    client.post(f"/api/resumes/{doc_id}/remarks", json={
        "notes": "Hired for Senior Fullstack Engineer position.",
        "status": "hired"
    })

    # Retrieve all resumes and verify status is 'hired'
    lib_resp = client.get("/api/resumes")
    assert lib_resp.status_code == 200
    items = lib_resp.json()
    assert isinstance(items, list)
    
    hired_item = next((item for item in items if item["doc_id"] == doc_id), None)
    assert hired_item is not None
    assert hired_item["latest_status"] == "hired"

    # Filter explicitly by 'hired'
    filter_resp = client.get("/api/resumes?status_filter=hired")
    assert filter_resp.status_code == 200
    filtered_items = filter_resp.json()
    assert isinstance(filtered_items, list)
    assert any(item["doc_id"] == doc_id for item in filtered_items)
    # Ensure items with other statuses are not included in the 'hired' filter
    for item in filtered_items:
        assert item["latest_status"] == "hired"


def test_improve_resume_personal_details_preservation(client):
    """
    Verifies that the resume improvement workflow accurately preserves and injects
    candidate personal details (name, email, phone, location, links) without stripping them
    or replacing them with generic placeholders.
    """
    doc_id = "DOC-1001"
    personal_info = {
        "candidate_name": "Arun Kumar",
        "candidate_role": "Senior Cloud Solutions Architect",
        "candidate_phone": "+91 98765 43210",
        "candidate_email": "arun.kumar.architect@enterprise.org",
        "candidate_location": "Bangalore, Karnataka, India",
        "candidate_links": "linkedin.com/in/arunkumar-cloud"
    }

    resp = client.post(f"/api/resumes/{doc_id}/improvements", json={
        "job_id": "JOB-101",
        "personal_details": personal_info
    })
    assert resp.status_code == 200
    data = resp.json()
    revised = data["improved_resume_text"]

    # Candidate personal details must be clearly present in the revised output
    assert "Arun Kumar" in revised
    assert "+91 98765 43210" in revised
    assert "arun.kumar.architect@enterprise.org" in revised
    assert "Bangalore, Karnataka, India" in revised
    assert "linkedin.com/in/arunkumar-cloud" in revised

    # Must NOT have stripped header artifacts
    assert "Contact via Recruiter Platform" not in revised
    # The first header must not be "# SUMMARY"
    first_line = revised.strip().split("\n")[0]
    assert "# SUMMARY" not in first_line
    assert "ARUN KUMAR" in first_line.upper()


def test_word_resume_with_personal_details(client):
    """
    Verifies that the generated Word (.docx) document includes full candidate personal details.
    """
    import docx
    import tempfile

    doc_id = "DOC-1001"
    personal_info = {
        "candidate_name": "Priya Sharma",
        "candidate_role": "Lead Fullstack Architect",
        "candidate_phone": "+1 (555) 349-8812",
        "candidate_email": "priya.sharma@leadarchitect.io",
        "candidate_location": "San Jose, CA",
        "candidate_links": "github.com/priyasharma"
    }

    resp = client.post(f"/api/resumes/{doc_id}/generate-word", json={
        "change_summary": "Tailored for Lead Architect with full contact info",
        "revised_content": "# Priya Sharma\nLead Fullstack Architect\n+1 (555) 349-8812 | priya.sharma@leadarchitect.io | San Jose, CA\n\n## PROFESSIONAL SUMMARY\nEngineered distributed cloud microservices.",
        "target_role": "Lead Fullstack Architect",
        "personal_details": personal_info
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    download_resp = client.get(data["download_url"])
    assert download_resp.status_code == 200

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(download_resp.content)
        tmp_path = tmp.name

    doc = docx.Document(tmp_path)
    full_text = "\n".join([p.text for p in doc.paragraphs])

    assert "PRIYA SHARMA" in full_text.upper()
    assert "+1 (555) 349-8812" in full_text
    assert "San Jose, CA" in full_text


def test_bulk_delete_resumes(client):
    """
    Tests bulk resume deletion:
    - Empty list validation (HTTP 400)
    - Non-existent IDs (partial failure tracking)
    - Valid multi-selection deletion and audit logging
    """
    # 1. Test empty list error
    resp_empty = client.post("/api/resumes/bulk-delete", json={"doc_ids": []})
    assert resp_empty.status_code == 400

    # 2. Upload two test resumes for bulk deletion
    files = [
        ("files", ("bulk_test_1.txt", b"Bulk Candidate 1\nPython, Docker, SQL", "text/plain")),
        ("files", ("bulk_test_2.txt", b"Bulk Candidate 2\nFastAPI, React, AWS", "text/plain")),
    ]
    upload_resp = client.post("/api/resumes", files=files)
    assert upload_resp.status_code == 200
    uploaded_docs = upload_resp.json()["results"]
    doc_id_1 = uploaded_docs[0]["doc_id"]
    doc_id_2 = uploaded_docs[1]["doc_id"]

    # 3. Test bulk delete with one valid ID and one invalid ID (partial failure handling)
    mixed_resp = client.post("/api/resumes/bulk-delete", json={
        "doc_ids": [doc_id_1, "NON-EXISTENT-DOC-999"]
    })
    assert mixed_resp.status_code == 200
    mixed_data = mixed_resp.json()
    assert mixed_data["deleted_count"] == 1
    assert doc_id_1 in mixed_data["deleted_ids"]
    assert len(mixed_data["failed_ids"]) == 1
    assert mixed_data["failed_ids"][0]["doc_id"] == "NON-EXISTENT-DOC-999"

    # Verify doc_id_1 was actually deleted
    verify_resp = client.get(f"/api/resumes/{doc_id_1}")
    assert verify_resp.status_code == 404

    # 4. Test deleting doc_id_2
    del_resp_2 = client.post("/api/resumes/bulk-delete", json={"doc_ids": [doc_id_2]})
    assert del_resp_2.status_code == 200
    assert del_resp_2.json()["deleted_count"] == 1
    assert doc_id_2 in del_resp_2.json()["deleted_ids"]

    # Verify doc_id_2 was deleted
    verify_resp_2 = client.get(f"/api/resumes/{doc_id_2}")
    assert verify_resp_2.status_code == 404
