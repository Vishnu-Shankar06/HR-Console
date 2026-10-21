from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, ForeignKey, JSON, Boolean
)
from sqlalchemy.orm import relationship
from app.models.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class Document(Base):
    __tablename__ = "documents"

    doc_id = Column(String(64), primary_key=True, index=True)
    dms_ref = Column(String(512), nullable=False)
    ikm_ref = Column(String(128), nullable=True)
    original_filename = Column(String(256), nullable=False)
    mime_type = Column(String(128), nullable=False)
    checksum = Column(String(64), nullable=False, index=True)
    upload_status = Column(String(32), default="uploaded", index=True)  # uploaded, processing, ready, failed
    uploaded_by = Column(String(64), default="recruiter-001")
    uploaded_at = Column(DateTime, default=utcnow)
    last_opened_at = Column(DateTime, default=utcnow)
    
    # Relationships
    profile = relationship("CandidateProfile", back_populates="document", uselist=False, cascade="all, delete-orphan")
    pii = relationship("CandidatePII", back_populates="document", uselist=False, cascade="all, delete-orphan")
    versions = relationship("ResumeVersion", back_populates="document", cascade="all, delete-orphan")
    actions = relationship("RecruitmentAction", back_populates="document", cascade="all, delete-orphan")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    doc_id = Column(String(64), ForeignKey("documents.doc_id"), primary_key=True)
    structured_profile_json = Column(JSON, nullable=False)
    raw_text_summary = Column(Text, nullable=True)
    extraction_version = Column(String(32), default="v1.0")
    profile_status = Column(String(32), default="ready", index=True)  # ready, needs_review, failed
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    document = relationship("Document", back_populates="profile")


class CandidatePII(Base):
    __tablename__ = "candidate_pii"

    doc_id = Column(String(64), ForeignKey("documents.doc_id"), primary_key=True)
    name_encrypted = Column(Text, nullable=True)
    email_encrypted = Column(Text, nullable=True)
    phone_encrypted = Column(Text, nullable=True)
    address_encrypted = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    document = relationship("Document", back_populates="pii")


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    job_id = Column(String(64), primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    source_ref = Column(String(256), nullable=True)
    raw_text = Column(Text, nullable=False)
    requirements_json = Column(JSON, nullable=False)
    created_by = Column(String(64), default="recruiter-001")
    created_at = Column(DateTime, default=utcnow)

    match_runs = relationship("MatchRun", back_populates="job")


class MatchRun(Base):
    __tablename__ = "match_runs"

    run_id = Column(String(64), primary_key=True, index=True)
    job_id = Column(String(64), ForeignKey("job_descriptions.job_id"), nullable=False)
    requested_count = Column(Integer, nullable=False)
    returned_count = Column(Integer, nullable=False)
    config_version = Column(String(32), default="standard-v1")
    created_by = Column(String(64), default="recruiter-001")
    created_at = Column(DateTime, default=utcnow)
    status = Column(String(32), default="completed")

    job = relationship("JobDescription", back_populates="match_runs")
    results = relationship("MatchResult", back_populates="match_run", cascade="all, delete-orphan")


class MatchResult(Base):
    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("match_runs.run_id"), index=True)
    doc_id = Column(String(64), ForeignKey("documents.doc_id"), index=True)
    rank = Column(Integer, nullable=False)
    score = Column(Float, nullable=False)
    score_breakdown_json = Column(JSON, nullable=False)
    evidence_json = Column(JSON, nullable=False)
    review_status = Column(String(32), default="pending")  # pending, reviewed, shortlisted, contacted, rejected

    match_run = relationship("MatchRun", back_populates="results")


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    version_id = Column(String(64), primary_key=True, index=True)
    doc_id = Column(String(64), ForeignKey("documents.doc_id"), index=True)
    dms_ref = Column(String(512), nullable=False)
    parent_version_id = Column(String(64), nullable=True)
    created_by = Column(String(64), default="recruiter-001")
    approved_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    change_summary = Column(Text, nullable=True)
    revised_content = Column(Text, nullable=True)

    document = relationship("Document", back_populates="versions")


class RecruitmentAction(Base):
    __tablename__ = "recruitment_actions"

    action_id = Column(String(64), primary_key=True, index=True)
    doc_id = Column(String(64), ForeignKey("documents.doc_id"), index=True)
    action_type = Column(String(64), nullable=False)  # uploaded, reviewed, contacted, shortlisted, rejected, improved, follow_up_scheduled
    status = Column(String(32), default="pending_review", index=True)  # pending_review, in_progress, contacted, shortlisted, rejected, closed
    owner_id = Column(String(64), default="recruiter-001")
    action_at = Column(DateTime, default=utcnow)
    notes = Column(Text, nullable=True)
    next_action_at = Column(DateTime, nullable=True, index=True)

    document = relationship("Document", back_populates="actions")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id = Column(String(64), primary_key=True, index=True)
    actor_id = Column(String(64), nullable=False)
    action = Column(String(64), nullable=False)  # e.g., view_pii, download_file, match_run, status_change
    target_doc_id = Column(String(64), nullable=True, index=True)
    timestamp = Column(DateTime, default=utcnow)
    outcome = Column(String(32), default="success")
    metadata_json = Column(JSON, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(64), primary_key=True, index=True)
    doc_id = Column(String(64), ForeignKey("documents.doc_id"), nullable=True, index=True)
    title = Column(String(256), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(32), default="warning")  # info, warning, danger
    days_inactive = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    is_read = Column(Boolean, default=False)
    email_sent = Column(Boolean, default=False)
    email_sent_to = Column(String(256), nullable=True)
    email_sent_at = Column(DateTime, nullable=True)
    email_attachment_filename = Column(String(256), nullable=True)

