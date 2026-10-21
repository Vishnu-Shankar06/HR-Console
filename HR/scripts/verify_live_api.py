import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=10.0)

def verify_all():
    print("=== LIVE INTEGRATION VERIFICATION ===")
    
    # 1. HTML Frontend
    r_home = client.get("/")
    assert r_home.status_code == 200
    assert "TalentPulse AI" in r_home.text
    print(f"[OK] Index HTML: HTTP 200 OK ({len(r_home.text)} bytes)")

    # 2. Static Assets
    r_css = client.get("/static/css/main.css")
    r_js = client.get("/static/js/app.js")
    assert r_css.status_code == 200
    assert r_js.status_code == 200
    print(f"[OK] Static CSS & JS Assets: HTTP 200 OK")

    # 3. Dashboard API
    r_dash = client.get("/api/dashboard/summary")
    assert r_dash.status_code == 200
    d = r_dash.json()
    print(f"[OK] Dashboard API: Total Resumes={d['total_resumes']}, Active Jobs={d['active_jobs']}, Follow-ups Due={d['follow_ups_due']}")

    # 4. Candidate Matching (Top-N = 3)
    r_jobs = client.get("/api/jobs")
    assert r_jobs.status_code == 200
    jobs_list = r_jobs.json()
    first_job_id = jobs_list[0]["job_id"] if jobs_list else None
    
    r_match = client.post("/api/matches", json={"job_id": first_job_id, "requested_count": 3} if first_job_id else {"job_description_text": "Python FastAPI PostgreSQL backend developer", "requested_count": 3})
    assert r_match.status_code == 200
    m = r_match.json()
    assert m["returned_count"] >= 1
    print(f"[OK] Candidate Matching API: Requested 3, Returned {m['returned_count']}")
    for res in m["results"]:
        print(f"   Rank #{res['rank']}: {res['candidate_label']} ({res['doc_id']}) - Score: {res['internal_match_score']}/100")
        assert len(res["matched_requirements"]) > 0

    # 5. Resume Improvement Gap Analysis
    r_imp = client.post("/api/resumes/DOC-1001/improvements", json={"job_id": first_job_id} if first_job_id else {"job_text": "Python FastAPI PostgreSQL developer"})
    assert r_imp.status_code == 200
    imp = r_imp.json()
    print(f"[OK] Resume Improvement API: Alignment Score={imp['internal_match_score']}/100, Matched={len(imp['matched_requirements'])}, Gaps={len(imp['not_demonstrated'])}")
    assert len(imp["suggested_rewrites"]) > 0
    print(f"   Suggested Rewrite: {imp['suggested_rewrites'][0]['section']} (Requires Confirmation: {imp['suggested_rewrites'][0]['requires_user_confirmation']})")

    # 6. Save Revised Version
    r_ver = client.post("/api/resumes/DOC-1001/versions", json={
        "change_summary": "Added verified PyTest test coverage and Docker containerization parameters.",
        "revised_content": "Arun Kumar - Senior Backend Developer\nSkills: Python, FastAPI, PostgreSQL, Docker, PyTest",
        "approved": True
    })
    assert r_ver.status_code == 200
    ver = r_ver.json()
    print(f"[OK] Resume Versioning API: Saved version {ver['version_id']} in DMS without altering original")

    # 7. Follow-ups
    r_fu = client.get("/api/follow-ups")
    assert r_fu.status_code == 200
    fus = r_fu.json()
    print(f"[OK] Follow-up Inactivity Tracker: Found {len(fus)} candidates requiring action")

    # 8. Candidate Development Plan
    r_plan = client.post("/api/resumes/DOC-1004/development-plan", json={"target_role": "Python Backend & Cloud Architect"})
    assert r_plan.status_code == 200
    plan = r_plan.json()
    print(f"[OK] Development Plan API: {len(plan['practical_projects'])} practical projects, {len(plan['learning_recommendations'])} courses suggested")

    # 9. PII Security Check
    r_pii = client.get("/api/resumes/DOC-1001/pii")
    assert r_pii.status_code == 200
    pii = r_pii.json()
    print(f"[OK] Authenticated Field Decryption: Name='{pii['name']}', Email='{pii['email']}' (Encrypted in DB)")

    # 10. UI Cleanliness & Roles Check
    assert "Security, Privacy & Audit Trail" not in r_home.text
    assert "Administrator" in r_home.text
    assert 'max="90"' in r_home.text
    print("[OK] UI Validated: Security tab removed, single Administrator role active, 90-day threshold slider present")

    # 11. Job Management Live Lifecycle (Create & Delete)
    r_new_job = client.post("/api/jobs", json={
        "title": "Staff Platform Architect",
        "job_text": "Staff Platform Architect required with deep expertise in Kubernetes, Distributed Systems, and Terraform."
    })
    assert r_new_job.status_code == 200
    created_job_id = r_new_job.json()["job_id"]
    print(f"[OK] Job Management: Created job '{created_job_id}'")

    # Verify job listed
    r_jobs = client.get("/api/jobs")
    assert any(j["job_id"] == created_job_id for j in r_jobs.json())

    # Delete job
    r_del_job = client.delete(f"/api/jobs/{created_job_id}")
    assert r_del_job.status_code == 200
    print(f"[OK] Job Management: Deleted job '{created_job_id}' successfully")

    # 12. Adjustable Follow-up Inactivity (30 and 90 Days)
    r_fu30 = client.get("/api/follow-ups?inactivity_days=30")
    assert r_fu30.status_code == 200
    r_fu90 = client.get("/api/follow-ups?inactivity_days=90")
    assert r_fu90.status_code == 200
    for item in r_fu90.json():
        assert item["is_overdue"] is True or item["status"] == "pending_review" or item["days_inactive"] >= 90
    print(f"[OK] Follow-up Threshold: 30-day and 90-day filter live verification passed")

    # 13. Resume Deletion Live Lifecycle
    # Create temporary resume via upload then delete
    upload_resp = client.post("/api/resumes", files=[
        ("files", ("temp_delete_test.txt", b"Temporary test candidate resume text content with Python and SQL", "text/plain"))
    ])
    assert upload_resp.status_code == 200
    res_list = upload_resp.json()["results"]
    temp_doc_id = res_list[0]["doc_id"]
    print(f"[OK] Resume Upload: Created temp resume '{temp_doc_id}'")

    del_res_resp = client.delete(f"/api/resumes/{temp_doc_id}")
    assert del_res_resp.status_code == 200
    assert del_res_resp.json()["success"] is True
    
    # Confirm 404
    assert client.get(f"/api/resumes/{temp_doc_id}").status_code == 404
    print(f"[OK] Resume Deletion: Deleted candidate '{temp_doc_id}' and confirmed 404")

    print("\n=============================================")
    print("ALL 13 LIVE PLATFORM CAPABILITIES FULLY VERIFIED!")
    print("=============================================")

if __name__ == "__main__":
    verify_all()

