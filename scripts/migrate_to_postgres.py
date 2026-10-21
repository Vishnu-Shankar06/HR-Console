import os
import sys
import sqlite3
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

# Set paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings, DB_DIR
from app.models.entities import (
    Base, Document, CandidateProfile, CandidatePII, JobDescription,
    MatchRun, MatchResult, ResumeVersion, RecruitmentAction, AuditEvent
)

PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "5433"))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASS = os.getenv("PG_PASS", "")
PG_DB = os.getenv("PG_DB", "recruitment")

SQLITE_PATH = DB_DIR / "recruitment.db"

def ensure_postgres_database():
    """Connects to default postgres database and ensures 'recruitment' exists with UTF-8."""
    print(f"Connecting to PostgreSQL server at {PG_HOST}:{PG_PORT} as {PG_USER}...")
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASS,
        dbname="postgres"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_DB,))
    exists = cur.fetchone()
    if exists:
        cur.execute("SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname = %s", (PG_DB,))
        enc = cur.fetchone()[0]
        if enc.upper() != "UTF8":
            print(f"Existing database {PG_DB} is {enc}, recreating with UTF8...")
            cur.execute(f'DROP DATABASE "{PG_DB}"')
            exists = None

    if not exists:
        print(f"Creating database '{PG_DB}' with UTF8 encoding from template0...")
        cur.execute(f"CREATE DATABASE \"{PG_DB}\" WITH TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C'")
        print(f"Database '{PG_DB}' created successfully.")
    else:
        print(f"Database '{PG_DB}' already exists and is UTF8.")
    cur.close()
    conn.close()

def migrate_data():
    """Migrates all records from SQLite to PostgreSQL preserving foreign keys and relationships."""
    ensure_postgres_database()

    pg_url = f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}" if PG_PASS else f"postgresql+psycopg2://{PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    print(f"Target PostgreSQL URL: {pg_url}")

    pg_engine = create_engine(pg_url, client_encoding="utf8")
    Base.metadata.create_all(pg_engine)
    print("PostgreSQL tables created or verified.")

    PgSession = sessionmaker(bind=pg_engine)
    pg_db = PgSession()

    if not SQLITE_PATH.exists():
        print(f"SQLite database not found at {SQLITE_PATH}. Nothing to migrate.")
        return

    sqlite_url = f"sqlite:///{SQLITE_PATH}"
    sqlite_engine = create_engine(sqlite_url)
    SqliteSession = sessionmaker(bind=sqlite_engine)
    sqlite_db = SqliteSession()

    print("Beginning migration from SQLite to PostgreSQL...")

    # Order of migration to respect foreign keys:
    # 1. Document
    # 2. CandidateProfile, CandidatePII
    # 3. JobDescription
    # 4. MatchRun
    # 5. MatchResult
    # 6. ResumeVersion
    # 7. RecruitmentAction
    # 8. AuditEvent

    # 1. Documents
    docs = sqlite_db.query(Document).all()
    print(f"Migrating {len(docs)} documents...")
    for doc in docs:
        if not pg_db.query(Document).filter(Document.doc_id == doc.doc_id).first():
            pg_db.add(Document(
                doc_id=doc.doc_id,
                dms_ref=doc.dms_ref,
                ikm_ref=doc.ikm_ref,
                original_filename=doc.original_filename,
                mime_type=doc.mime_type,
                checksum=doc.checksum,
                upload_status=doc.upload_status,
                uploaded_by=doc.uploaded_by,
                uploaded_at=doc.uploaded_at,
                last_opened_at=doc.last_opened_at
            ))
    pg_db.commit()

    # 2. Candidate Profiles
    profiles = sqlite_db.query(CandidateProfile).all()
    print(f"Migrating {len(profiles)} candidate profiles...")
    for p in profiles:
        if not pg_db.query(CandidateProfile).filter(CandidateProfile.doc_id == p.doc_id).first():
            pg_db.add(CandidateProfile(
                doc_id=p.doc_id,
                structured_profile_json=p.structured_profile_json,
                raw_text_summary=p.raw_text_summary,
                extraction_version=p.extraction_version,
                profile_status=p.profile_status,
                updated_at=p.updated_at
            ))
    pg_db.commit()

    # 3. Candidate PII
    piis = sqlite_db.query(CandidatePII).all()
    print(f"Migrating {len(piis)} candidate PII records...")
    for pii in piis:
        if not pg_db.query(CandidatePII).filter(CandidatePII.doc_id == pii.doc_id).first():
            pg_db.add(CandidatePII(
                doc_id=pii.doc_id,
                name_encrypted=pii.name_encrypted,
                email_encrypted=pii.email_encrypted,
                phone_encrypted=pii.phone_encrypted,
                address_encrypted=pii.address_encrypted,
                updated_at=pii.updated_at
            ))
    pg_db.commit()

    # 4. Job Descriptions
    jobs = sqlite_db.query(JobDescription).all()
    print(f"Migrating {len(jobs)} job descriptions...")
    for job in jobs:
        if not pg_db.query(JobDescription).filter(JobDescription.job_id == job.job_id).first():
            pg_db.add(JobDescription(
                job_id=job.job_id,
                title=job.title,
                source_ref=job.source_ref,
                raw_text=job.raw_text,
                requirements_json=job.requirements_json,
                created_by=job.created_by,
                created_at=job.created_at
            ))
    pg_db.commit()

    # 5. Match Runs
    runs = sqlite_db.query(MatchRun).all()
    print(f"Migrating {len(runs)} match runs...")
    for run in runs:
        if not pg_db.query(MatchRun).filter(MatchRun.run_id == run.run_id).first():
            pg_db.add(MatchRun(
                run_id=run.run_id,
                job_id=run.job_id,
                requested_count=run.requested_count,
                returned_count=run.returned_count,
                config_version=run.config_version,
                created_by=run.created_by,
                created_at=run.created_at,
                status=run.status
            ))
    pg_db.commit()

    # 6. Match Results
    results = sqlite_db.query(MatchResult).all()
    print(f"Migrating {len(results)} match results...")
    for r in results:
        existing = pg_db.query(MatchResult).filter(
            MatchResult.run_id == r.run_id,
            MatchResult.doc_id == r.doc_id
        ).first()
        if not existing:
            pg_db.add(MatchResult(
                run_id=r.run_id,
                doc_id=r.doc_id,
                rank=r.rank,
                score=r.score,
                score_breakdown_json=r.score_breakdown_json,
                evidence_json=r.evidence_json,
                review_status=r.review_status
            ))
    pg_db.commit()

    # 7. Resume Versions
    versions = sqlite_db.query(ResumeVersion).all()
    print(f"Migrating {len(versions)} resume versions...")
    for v in versions:
        if not pg_db.query(ResumeVersion).filter(ResumeVersion.version_id == v.version_id).first():
            pg_db.add(ResumeVersion(
                version_id=v.version_id,
                doc_id=v.doc_id,
                dms_ref=v.dms_ref,
                parent_version_id=v.parent_version_id,
                created_by=v.created_by,
                approved_by=v.approved_by,
                created_at=v.created_at,
                change_summary=v.change_summary,
                revised_content=v.revised_content
            ))
    pg_db.commit()

    # 8. Recruitment Actions
    actions = sqlite_db.query(RecruitmentAction).all()
    print(f"Migrating {len(actions)} recruitment actions...")
    for a in actions:
        if not pg_db.query(RecruitmentAction).filter(RecruitmentAction.action_id == a.action_id).first():
            pg_db.add(RecruitmentAction(
                action_id=a.action_id,
                doc_id=a.doc_id,
                action_type=a.action_type,
                status=a.status,
                owner_id=a.owner_id,
                action_at=a.action_at,
                notes=a.notes,
                next_action_at=a.next_action_at
            ))
    pg_db.commit()

    # 9. Audit Events
    audits = sqlite_db.query(AuditEvent).all()
    print(f"Migrating {len(audits)} audit events...")
    for aud in audits:
        if not pg_db.query(AuditEvent).filter(AuditEvent.event_id == aud.event_id).first():
            pg_db.add(AuditEvent(
                event_id=aud.event_id,
                actor_id=aud.actor_id,
                action=aud.action,
                target_doc_id=aud.target_doc_id,
                timestamp=aud.timestamp,
                outcome=aud.outcome,
                metadata_json=aud.metadata_json
            ))
    pg_db.commit()

    # 10. Notifications
    from app.models.entities import Notification
    notifications = sqlite_db.query(Notification).all()
    print(f"Migrating {len(notifications)} notifications...")
    for n in notifications:
        if not pg_db.query(Notification).filter(Notification.id == n.id).first():
            pg_db.add(Notification(
                id=n.id,
                doc_id=n.doc_id,
                title=n.title,
                message=n.message,
                severity=n.severity,
                days_inactive=n.days_inactive,
                created_at=n.created_at,
                is_read=n.is_read,
                email_sent=n.email_sent,
                email_sent_to=n.email_sent_to,
                email_sent_at=n.email_sent_at,
                email_attachment_filename=n.email_attachment_filename
            ))
    pg_db.commit()

    # Verification
    print("\n--- Migration Verification ---")
    print(f"Documents: SQLite={len(docs)}, Postgres={pg_db.query(Document).count()}")
    print(f"Candidate Profiles: SQLite={len(profiles)}, Postgres={pg_db.query(CandidateProfile).count()}")
    print(f"Candidate PII: SQLite={len(piis)}, Postgres={pg_db.query(CandidatePII).count()}")
    print(f"Job Descriptions: SQLite={len(jobs)}, Postgres={pg_db.query(JobDescription).count()}")
    print(f"Match Runs: SQLite={len(runs)}, Postgres={pg_db.query(MatchRun).count()}")
    print(f"Resume Versions: SQLite={len(versions)}, Postgres={pg_db.query(ResumeVersion).count()}")
    print(f"Recruitment Actions: SQLite={len(actions)}, Postgres={pg_db.query(RecruitmentAction).count()}")
    print(f"Audit Events: SQLite={len(audits)}, Postgres={pg_db.query(AuditEvent).count()}")
    print("\nData migration to PostgreSQL completed successfully!")

    sqlite_db.close()
    pg_db.close()

if __name__ == "__main__":
    migrate_data()
