import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models.entities import Document, CandidateProfile, CandidatePII, JobDescription, RecruitmentAction, AuditEvent
from app.integrations.dms_adapter import dms_adapter
from app.integrations.neo4j_repository import neo4j_repository
from app.security.encryption import pii_crypto

SAMPLE_CANDIDATES = [
    {
        "doc_id": "DOC-1001",
        "name": "Arun Kumar",
        "email": "arun.kumar.dev@example.com",
        "phone": "+91-9876543210",
        "address": "Bengaluru, Karnataka",
        "filename": "resume_arun_backend.pdf",
        "skills": ["Python", "FastAPI", "PostgreSQL", "REST APIs", "SQLAlchemy", "Docker", "Git"],
        "qualifications": [{"name": "B.Tech", "field": "Computer Science & Engineering"}],
        "experience": [
            {"role": "Backend Developer", "evidence": "Built scalable REST API microservices with FastAPI and PostgreSQL handling 5M requests/day."}
        ],
        "projects": [
            {"name": "E-Commerce Payment Gateway API", "evidence": "Engineered idempotent payment processing endpoints using FastAPI, PostgreSQL, and Redis."}
        ],
        "certifications": [{"name": "AWS Certified Developer - Associate", "issuer": "AWS"}],
        "days_inactive": 16,
        "status": "pending_review",
        "action_type": "uploaded",
        "notes": "Candidate uploaded 16 days ago; no review recorded yet."
    },
    {
        "doc_id": "DOC-1002",
        "name": "Priya Sharma",
        "email": "priya.sharma.tech@example.com",
        "phone": "+91-9876501234",
        "address": "Pune, Maharashtra",
        "filename": "resume_priya_fullstack.docx",
        "skills": ["Python", "FastAPI", "PostgreSQL", "React", "TypeScript", "REST APIs", "TailwindCSS"],
        "qualifications": [{"name": "M.Tech", "field": "Information Technology"}],
        "experience": [
            {"role": "Full Stack Engineer", "evidence": "Developed responsive user interfaces with React and built performant FastAPI backend endpoints."}
        ],
        "projects": [
            {"name": "Healthcare Teleconsultation Portal", "evidence": "Integrated real-time appointment booking with PostgreSQL schema optimization."}
        ],
        "certifications": [],
        "days_inactive": 10,
        "status": "pending_review",
        "action_type": "uploaded",
        "notes": "Pending recruiter initial screening."
    },
    {
        "doc_id": "DOC-1003",
        "name": "Vikram Patel",
        "email": "vikram.patel.cloud@example.com",
        "phone": "+91-9812345678",
        "address": "Hyderabad, Telangana",
        "filename": "resume_vikram_devops.pdf",
        "skills": ["Python", "Docker", "Kubernetes", "AWS", "CI/CD", "Linux", "Git"],
        "qualifications": [{"name": "B.E.", "field": "Computer Science"}],
        "experience": [
            {"role": "DevOps Engineer", "evidence": "Automated deployment pipelines using GitHub Actions and managed multi-node Kubernetes clusters."}
        ],
        "projects": [
            {"name": "Infrastructure as Code Pipeline", "evidence": "Provisioned automated AWS environments with Docker and Terraform."}
        ],
        "certifications": [{"name": "Kubernetes CKA", "issuer": "Linux Foundation"}],
        "days_inactive": 4,
        "status": "contacted",
        "action_type": "contacted",
        "notes": "Sent introductory email; follow up scheduled next week."
    },
    {
        "doc_id": "DOC-1004",
        "name": "Ananya Sen",
        "email": "ananya.sen.ai@example.com",
        "phone": "+91-9845678901",
        "address": "Kolkata, West Bengal",
        "filename": "resume_ananya_data.pdf",
        "skills": ["Python", "Pandas", "NumPy", "SQL", "PostgreSQL", "PyTorch", "FastAPI"],
        "qualifications": [{"name": "B.Tech", "field": "Artificial Intelligence & Data Science"}],
        "experience": [
            {"role": "Data Scientist", "evidence": "Built analytical pipelines and machine learning inference endpoints using FastAPI."}
        ],
        "projects": [
            {"name": "Customer Churn Prediction Model", "evidence": "Trained predictive models and exposed REST prediction endpoints."}
        ],
        "certifications": [],
        "days_inactive": 20,
        "status": "pending_review",
        "action_type": "uploaded",
        "notes": "Uploaded 20 days ago; overdue for screening."
    },
    {
        "doc_id": "DOC-1005",
        "name": "Rohit Gupta",
        "email": "rohit.gupta.fe@example.com",
        "phone": "+91-9765432109",
        "address": "Delhi NCR",
        "filename": "resume_rohit_frontend.docx",
        "skills": ["React", "TypeScript", "JavaScript", "Next.js", "HTML5", "CSS3", "Git"],
        "qualifications": [{"name": "BCA", "field": "Computer Applications"}],
        "experience": [
            {"role": "Frontend Developer", "evidence": "Engineered modern responsive web apps using React, Next.js, and TypeScript."}
        ],
        "projects": [
            {"name": "Analytics Dashboard UI", "evidence": "Built high-performance charting interfaces with interactive filters."}
        ],
        "certifications": [],
        "days_inactive": 1,
        "status": "reviewed",
        "action_type": "reviewed",
        "notes": "Portfolio verified."
    },
    {
        "doc_id": "DOC-1006",
        "name": "Sneha Reddy",
        "email": "sneha.reddy.py@example.com",
        "phone": "+91-9887766554",
        "address": "Chennai, Tamil Nadu",
        "filename": "resume_sneha_python.pdf",
        "skills": ["Python", "Django", "PostgreSQL", "REST APIs", "Redis", "Celery", "PyTest"],
        "qualifications": [{"name": "B.Tech", "field": "Computer Science"}],
        "experience": [
            {"role": "Backend Engineer", "evidence": "Architected asynchronous worker queues using Celery and Redis with Django REST framework."}
        ],
        "projects": [
            {"name": "Notification Engine", "evidence": "Dispatched 1M+ daily notifications with high reliability and PyTest test coverage."}
        ],
        "certifications": [],
        "days_inactive": 12,
        "status": "shortlisted",
        "action_type": "shortlisted",
        "notes": "Shortlisted for Senior Python Developer role; interview follow-up overdue."
    }
]

SAMPLE_JOBS = [
    {
        "job_id": "JOB-101",
        "title": "Senior Python Backend Developer",
        "raw_text": """Job Title: Senior Python Backend Developer
Location: Remote / Hybrid
Role Overview:
We are seeking an experienced Python Backend Developer to design, build, and maintain mission-critical RESTful APIs and distributed backend services.

Key Requirements:
- Mandatory: Strong proficiency in Python with FastAPI or Django.
- Database: Solid hands-on experience with PostgreSQL, schema design, and query optimization.
- APIs: Proven expertise building high-performance REST APIs.
- Cloud & Infrastructure: Familiarity with Docker containerization and cloud deployments (AWS/GCP).
- Testing: Writing robust unit and integration tests using PyTest.
- Experience: 2+ years building backend systems in production environments.
""",
        "requirements": {
            "title": "Senior Python Backend Developer",
            "mandatory_requirements": [
                "Python proficiency",
                "REST API & backend framework experience (FastAPI / Django)",
                "Relational database design (PostgreSQL)"
            ],
            "technical_skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "REST APIs", "PyTest", "AWS"],
            "experience_requirements": ["2+ years of backend development experience"],
            "qualification_requirements": ["Degree in Computer Science or proven engineering track record"],
            "preferred_skills": ["Docker", "AWS", "Redis", "CI/CD"]
        }
    },
    {
        "job_id": "JOB-102",
        "title": "Full Stack Engineer (React + FastAPI)",
        "raw_text": """Job Title: Full Stack Engineer
Role Overview:
Join our product engineering team to build customer-facing web applications using React, TypeScript, and modern Python FastAPI microservices.

Requirements:
- Frontend: Strong foundation in React, TypeScript, and modern CSS.
- Backend: Practical experience building Python REST APIs with FastAPI.
- Database: Experience working with PostgreSQL or relational databases.
- Collaboration: Git version control and agile product delivery.
""",
        "requirements": {
            "title": "Full Stack Engineer (React + FastAPI)",
            "mandatory_requirements": [
                "React & TypeScript proficiency",
                "FastAPI REST backend development",
                "PostgreSQL database integration"
            ],
            "technical_skills": ["React", "TypeScript", "Python", "FastAPI", "PostgreSQL", "Git", "REST APIs"],
            "experience_requirements": ["2+ years full stack engineering"],
            "qualification_requirements": ["Bachelor's in CS / IT or relevant portfolio"],
            "preferred_skills": ["Next.js", "Docker", "TailwindCSS"]
        }
    }
]

def seed_database_if_empty(db: Session):
    """Populates initial synthetic candidates and sample jobs if empty or missing."""
    now = datetime.now(timezone.utc)
    from app.config import settings
    from app.integrations.ikm_adapter import ikm_adapter

    # 1. Seed Candidates & populate in-memory preview cache
    for c in SAMPLE_CANDIDATES:
        doc_id = c["doc_id"]
        # Use actual sample document bytes from sample_data/resumes if available (zero disk persistence in storage)
        sample_file = settings.BASE_DIR / "sample_data" / "resumes" / c["filename"]
        if sample_file.exists():
            file_bytes = sample_file.read_bytes()
        else:
            file_bytes = f"Resume Content for {c['name']}\nSkills: {', '.join(c['skills'])}\n".encode("utf-8")
        
        dms_ref = f"ikm://{doc_id}"
        checksum = dms_adapter.calculate_checksum(file_bytes)
        if hasattr(ikm_adapter, "_download_cache"):
            ikm_adapter._download_cache[f"ikm-{doc_id}"] = file_bytes
            ikm_adapter._download_cache[doc_id] = file_bytes
            ikm_adapter._download_cache[dms_ref] = file_bytes
            ikm_adapter._download_cache[c["filename"].lower()] = file_bytes

        # If candidate already exists in database, skip adding
        if db.query(Document).filter(Document.doc_id == doc_id).first():
            continue

        # Encrypt PII
        encrypted_pii = pii_crypto.encrypt_pii_dict({
            "name": c["name"],
            "email": c["email"],
            "phone": c["phone"],
            "address": c["address"]
        })

        # Structured profile
        profile_json = {
            "doc_id": doc_id,
            "skills": c["skills"],
            "qualifications": c["qualifications"],
            "experience": c["experience"],
            "projects": c["projects"],
            "certifications": c["certifications"],
            "profile_status": "ready",
            "source_document_ref": dms_ref
        }

        uploaded_at = now - timedelta(days=c["days_inactive"])

        # Document
        doc = Document(
            doc_id=doc_id,
            dms_ref=dms_ref,
            ikm_ref=f"ikm-{doc_id}",
            original_filename=c["filename"],
            mime_type="application/pdf" if c["filename"].endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            checksum=checksum,
            upload_status="ready",
            uploaded_by="recruiter-001",
            uploaded_at=uploaded_at
        )
        db.add(doc)

        # Profile
        profile_rec = CandidateProfile(
            doc_id=doc_id,
            structured_profile_json=profile_json,
            raw_text_summary=f"{c['name']} - {c['experience'][0]['role']}. Skills: {', '.join(c['skills'])}",
            profile_status="ready",
            updated_at=uploaded_at
        )
        db.add(profile_rec)

        # PII
        pii_rec = CandidatePII(
            doc_id=doc_id,
            name_encrypted=encrypted_pii["name_encrypted"],
            email_encrypted=encrypted_pii["email_encrypted"],
            phone_encrypted=encrypted_pii["phone_encrypted"],
            address_encrypted=encrypted_pii["address_encrypted"],
            updated_at=uploaded_at
        )
        db.add(pii_rec)

        # Initial Recruitment Action
        act_time = now - timedelta(days=c["days_inactive"])
        next_due = None
        if c["status"] == "shortlisted":
            next_due = now - timedelta(days=2)  # Overdue for test
        elif c["status"] == "contacted":
            next_due = now + timedelta(days=3)  # Due in 3 days

        act = RecruitmentAction(
            action_id=f"act-{uuid.uuid4().hex[:8]}",
            doc_id=doc_id,
            action_type=c["action_type"],
            status=c["status"],
            owner_id="recruiter-001",
            notes=c["notes"],
            action_at=act_time,
            next_action_at=next_due
        )
        db.add(act)

        # Graph synchronization
        try:
            neo4j_repository.sync_candidate_profile(doc_id, profile_json, dms_ref)
        except Exception:
            pass

    # 2. Seed Jobs if missing
    for j in SAMPLE_JOBS:
        if db.query(JobDescription).filter(JobDescription.job_id == j["job_id"]).first():
            continue
        job = JobDescription(
            job_id=j["job_id"],
            title=j["title"],
            source_ref="seed_standard",
            raw_text=j["raw_text"],
            requirements_json=j["requirements"],
            created_by="recruiter-001",
            created_at=now - timedelta(days=5)
        )
        db.add(job)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
