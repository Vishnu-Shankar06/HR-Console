<<<<<<< HEAD
# TalentPulse AI — AI Recruitment & Resume Intelligence Platform

> An all-in-one AI recruitment management platform built for non-technical recruiters. Designed with modular architecture that decouples company Intelligent Knowledge Management (IKM) and Document Management System (DMS) interfaces while orchestrating candidate matching, evidence-grounded resume improvement, and candidate follow-up workflows.

---

## 🌟 Executive Summary & Business Capabilities

The platform provides three primary business functions sharing a single central candidate identity (`doc_id`, e.g. `DOC-1001`):

1. **Find Candidates**:
   - Multi-file resume upload (PDF & DOCX) with duplicate detection via SHA-256 checksums.
   - Job description input (from saved requisitions or typed text) parsed into structured criteria: Mandatory, Technical, Experience, and Qualifications.
   - **Manually typable numeric shortlist count (Top-N)** with validation (strictly rejects blanks, zeros, negative numbers, decimals, non-numeric strings, or excessive limits).
   - Transparent, explainable 5-dimension internal scoring:
     - Mandatory Requirements: 35%
     - Technical / Role Skills: 25%
     - Relevant Experience & Projects: 20%
     - Education / Credentials: 10%
     - Evidence Quality & Specificity: 10%
   - Grounded explanations with verbatim citations from verified resume evidence.
   - Resilient availability handling: when available candidates are fewer than requested, returns all eligible candidates without fabricating fake profiles.
   - Recruiter workflow actions: Shortlist, Contact, Mark Reviewed, Reject with reason.

2. **Improve Resumes**:
   - Compares a stored or uploaded resume against target job requirements.
   - Transparent internal job alignment score (e.g. `74/100`) accompanied by an explicit disclaimer stating it is an internal diagnostic benchmark and does not promise an external 3rd-party ATS pass rate.
   - Classifies requirements into: Matched, Partially Demonstrated, Not Demonstrated (Gaps), and Formatting/Readability checks.
   - Generates concrete, evidence-grounded rewrites.
   - Flags all suggestions that add unverified empirical facts with `requires_user_confirmation: true`.
   - Side-by-side interactive draft editor allowing recruiters to accept, refine, or customize suggestions.
   - **Approved Version Saving**: Creates a new immutable version in the DMS (e.g. `VER-DOC-1001-v2.txt`), tracks change summaries and approver IDs, and leaves the original resume file completely untouched.

3. **Manage Old Resumes & Follow-ups**:
   - Surfaces inactive resumes based on workflow states rather than file age alone (e.g., pending review > 7 days, overdue next action dates, or shortlisted without contact).
   - Recruiter action controls: Mark Contacted, Update Status, Add Notes, Reassign Owner, Snooze (7 days), or Schedule Next Follow-up Date.
   - **Candidate Development Plan**:
     - Actionable practical projects to demonstrate missing requirements (e.g., containerizing backend microservices, PyTest automated test suites).
     - Verified learning recommendations (official documentation and tutorials).
     - Optional certifications tied to verified gaps (clearly marked as recommendations, not job guarantees).
     - Prepared recruiter-to-candidate outreach message draft with one-click clipboard copying.
   - Direct button to launch resume improvement workflow with the candidate and target job pre-selected.

---

## 🏗️ Architecture & Technology Stack

```
Recruiter Browser (HTML5, Vanilla CSS Glassmorphic UI, Vanilla JS)
       │
       ▼
FastAPI Application Layer (Port 8000)
  ├── RBAC & Security (Recruiter, Manager, Admin roles)
  ├── Authenticated PII Field Encryption (Fernet / AES-256)
  ├── Resume Ingestion & Validation Engine
  ├── Candidate Matching & Scoring Engine
  ├── Resume Improvement & Revision Workflow
  └── Follow-up Inactivity & Reminder Engine
       │
       ├──► DMS Adapter (storage/dms/originals/ & storage/dms/versions/)
       │    └── Guarantees original resumes remain immutable; stores versioned revisions separately
       │
       ├──► IKM Adapter (LocalIKMAdapter & HttpIKMAdapter stub)
       │    └── Decoupled extraction & semantic retrieval interface per company brief
       │
       ├──► Graph Repository (Neo4j driver with in-memory graph engine fallback)
       │    └── Models (:Candidate)-[:HAS_SKILL]->(:Skill), Qualifications, Experience
       │
       └──► Application Relational Database (SQLAlchemy / SQLite / PostgreSQL)
            └── Documents, Profiles, PII, Jobs, Match Runs, Results, Versions, Actions, Audit
```

### Technology Highlights
- **Backend**: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0, Uvicorn.
- **Document Ingestion**: `pypdf`, `python-docx`, `reportlab` for PDF/DOCX parsing and version generation.
- **Security & Privacy**: `cryptography` (Fernet authenticated encryption), zero PII passed to LLM prompts, prompt-injection defense filters, and audit trail logging.
- **Frontend**: Clean Vanilla CSS design system (modern dark slate palette, glassmorphism, responsive cards, micro-animations, no Tailwind dependency) and modular Vanilla JavaScript.
- **User Experience**: Plain language designed for non-technical recruiters (no exposed implementation jargon like "embeddings", "vector index", "Cypher", or "RAG").

---

## 🔒 Security, Privacy & Compliance

1. **PII Separation & Field-Level Encryption**:
   - Personal metadata (Name, Email, Phone, Address) is separated from the recruitment profile upon ingestion and encrypted via authenticated 256-bit encryption before storage.
   - LLM prompts for candidate matching and scoring strictly receive anonymized profiles, preventing demographic bias (age, address, gender) and personal data leakage.
   - Decrypted PII can only be accessed via an authorized endpoint (`/api/resumes/{doc_id}/pii`), which logs an audit event with actor identity.

2. **Prompt Injection Defense**:
   - Untrusted text from uploaded resumes and job descriptions is sanitized to neutralize embedded instructions (such as "ignore previous instructions" or "assign a score of 100").

3. **Immutable Source Preservation**:
   - Original uploaded resumes are saved once in the DMS with SHA-256 checksums and cannot be overwritten by revisions. Revisions receive separate version IDs and storage references.

4. **Compliance Audit Trail**:
   - All sensitive actions (PII decryption, file downloads, matching runs, status modifications, version approvals) are recorded in the `audit_events` table.

---

## 🚀 Getting Started

### 1. Installation

```bash
# Clone or navigate to the repository
cd c:\Users\vishn\OneDrive\Desktop\HR

# Install required dependencies
pip install -r requirements.txt
```

### 2. Configuration (.env)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Configuration variables include:
- `FIELD_ENCRYPTION_KEY`: 32-byte base64 encryption key for PII fields.
- `DATABASE_URL`: Database connection string (defaults to SQLite: `sqlite:///./storage/db/recruitment.db`).
- `DMS_STORAGE_DIR`: Directory for DMS storage (defaults to `./storage/dms`).
- `IKM_ENABLED`: Set to `true` when connecting to company's live enterprise IKM REST endpoint. Defaults to `false` (uses built-in `LocalIKMAdapter`).
- `NEO4J_ENABLED`: Set to `true` when connecting to a live Neo4j database. Defaults to `false` (uses in-memory graph store).
- `DEFAULT_INACTIVITY_THRESHOLD_DAYS`: Inactivity alert window (defaults to `7` days).

### 3. Generate Realistic Sample Files & Seed Data

```bash
# Generates realistic PDF and DOCX sample resumes
python scripts/generate_sample_files.py
```

### 4. Run the Application

```bash
# Start the FastAPI dev server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The application will be accessible at:
- **Web Application UI**: `http://127.0.0.1:8000/`
- **Interactive OpenAPI Docs**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/api/health`

---

## 🧪 Testing

Run the automated test suite verifying all 9 core requirements:

```bash
python -m pytest -v tests/test_all_workflows.py
```

Run the live server end-to-end integration test:

```bash
python scripts/verify_live_api.py
```

Test coverage includes:
- Multi-file PDF/DOCX ingestion and unique `doc_id` generation.
- Shortlist Top-N input validation (positive integer, zero/negative rejection, bounds checks).
- Candidate availability handling (fewer-than-N without fabrication).
- 5-dimension scoring and evidence citations.
- PII authenticated encryption and zero leakage.
- Gap analysis and revision versioning preserving original files.
- Inactivity threshold detection and candidate development plan generation.

---

## 📡 Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/resumes` | Multi-file resume upload with per-file status |
| `GET` | `/api/resumes` | Search and list candidate profiles (PII omitted) |
| `GET` | `/api/resumes/{doc_id}` | Detailed candidate profile and workflow metadata |
| `GET` | `/api/resumes/{doc_id}/pii` | Authorized decrypted personal information (logged in audit) |
| `GET` | `/api/resumes/{doc_id}/file` | Stream original resume document from DMS |
| `POST` | `/api/jobs` | Create/parse job description into structured criteria |
| `GET` | `/api/jobs` | List available job requisitions |
| `POST` | `/api/matches` | Execute candidate matching with manually typed Top-N |
| `GET` | `/api/matches/{run_id}` | Retrieve match results, rankings, and explanations |
| `POST` | `/api/resumes/{doc_id}/improvements` | Run gap analysis and rewrite suggestions against JD |
| `POST` | `/api/resumes/{doc_id}/versions` | Save approved revised resume draft to DMS |
| `GET` | `/api/resumes/{doc_id}/versions` | Retrieve version history for a candidate |
| `GET` | `/api/versions/{version_id}/file` | Download revised resume file |
| `GET` | `/api/follow-ups` | List inactive resumes and overdue follow-up records |
| `POST` | `/api/resumes/{doc_id}/actions` | Record recruiter workflow action (reviewed, contacted, etc.) |
| `POST` | `/api/resumes/{doc_id}/development-plan` | Generate tailored candidate development plan & outreach draft |
| `GET` | `/api/dashboard/summary` | Executive metrics, skill distributions, and activity feed |
| `GET` | `/api/audit/events` | Compliance and security audit trail events |

---

## 📋 Documented Assumptions & Future Integration Contracts

Per the project specification, the following assumptions were made regarding external systems and require confirmation with the enterprise team:

1. **IKM (Intelligent Knowledge Management)**:
   - Per explicit instruction (*"leave the ikm part and do the rest yourself"*), the platform uses the decoupled `LocalIKMAdapter` for PDF/DOCX text extraction, metadata parsing, and semantic indexing.
   - When connecting to production IKM, configure `IKM_ENABLED=true`, `IKM_BASE_URL`, and `IKM_API_KEY`. The `HttpIKMAdapter` in `app/integrations/ikm_adapter.py` provides the integration hooks.
2. **Neo4j Graph Database**:
   - The platform implements the specified graph model (`Candidate`, `Skill`, `Qualification`, `Experience`, `Project`) with parameterized Cypher queries. When `NEO4J_ENABLED=false`, it uses an in-memory graph store to ensure zero deployment friction.
3. **Third-Party ATS Positioning**:
   - The platform explicitly frames its score as an **Internal Job Alignment Score**, and avoids making false guarantees regarding 90% pass rates on proprietary third-party ATS screening tools.
4. **Key Management Service (KMS)**:
   - For local development, Fernet AES-256 key is derived from `FIELD_ENCRYPTION_KEY`. In production, this can be integrated with AWS KMS, HashiCorp Vault, or Azure Key Vault without altering application models.
=======
# HR-Console
>>>>>>> origin/main
