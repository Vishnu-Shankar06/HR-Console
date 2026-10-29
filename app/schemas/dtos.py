from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

# --- Document & Ingestion Schemas ---

class UploadResultItem(BaseModel):
    filename: str
    doc_id: Optional[str] = None
    status: str  # uploaded, processing, ready, failed, duplicate
    error: Optional[str] = None
    checksum: Optional[str] = None

class MultiUploadResponse(BaseModel):
    total_files: int
    successful_count: int
    failed_count: int
    results: List[UploadResultItem]

class CandidatePIIDTO(BaseModel):
    doc_id: str
    name: Optional[str] = None
    title: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    links: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    filename: Optional[str] = None
    uploaded_at: Optional[str] = None
    experience_years: Optional[float] = None
    experience_display: Optional[str] = None
    experience_details: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    skills: List[str] = []
    employment: List[Dict[str, Any]] = []

class CandidateProfileDTO(BaseModel):
    doc_id: str
    title: Optional[str] = None
    role: Optional[str] = None
    summary: Optional[str] = None
    skills: List[str] = []
    qualifications: List[Dict[str, Any]] = []
    experience: List[Dict[str, Any]] = []
    projects: List[Dict[str, Any]] = []
    certifications: List[Dict[str, Any]] = []
    profile_status: str
    source_document_ref: str
    raw_text_summary: Optional[str] = None
    experience_years: Optional[float] = None
    experience_display: Optional[str] = None
    experience_details: Optional[Dict[str, Any]] = None
    location: Optional[str] = None
    links: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None

class DocumentDetailResponse(BaseModel):
    doc_id: str
    original_filename: str
    upload_status: str
    uploaded_at: datetime
    uploaded_by: str
    profile: Optional[CandidateProfileDTO] = None
    latest_status: Optional[str] = None
    status: Optional[str] = None
    next_action_at: Optional[datetime] = None
    versions_count: int = 0
    full_name: Optional[str] = None
    pii: Optional[CandidatePIIDTO] = None

# --- Job Description Schemas ---

class JobCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=256)
    job_text: str = Field(..., min_length=10)

class JobResponse(BaseModel):
    job_id: str
    title: str
    created_at: datetime
    created_by: str
    requirements: Dict[str, Any]
    preview_snippet: str

# --- Candidate Matching Schemas ---

class MatchRequest(BaseModel):
    job_id: Optional[str] = None
    job_description_text: Optional[str] = None
    requested_count: int = Field(..., description="Manually entered top-N candidates")
    filters: Optional[Dict[str, Any]] = None
    doc_ids: Optional[List[str]] = None

    @field_validator("requested_count")
    @classmethod
    def validate_positive_integer(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Requested candidate count must be a positive integer greater than 0.")
        if v > 100:
            raise ValueError("Requested candidate count exceeds maximum allowed limit of 100.")
        return v

class MatchedRequirement(BaseModel):
    requirement: str
    evidence: str
    category: Optional[str] = "skill"

class MatchGap(BaseModel):
    requirement: str
    status: str  # not_demonstrated, partially_demonstrated, unclear
    recommendation: Optional[str] = None

class MatchResultItem(BaseModel):
    rank: int
    doc_id: str
    candidate_label: str  # e.g., "Candidate DOC-1001" or authorized name
    candidate_name: Optional[str] = None
    full_name: Optional[str] = None
    internal_match_score: int
    score_breakdown: Dict[str, Any]
    matched_requirements: List[MatchedRequirement]
    gaps: List[MatchGap]
    explanation: str
    review_required: bool = True
    current_status: Optional[str] = None
    pii: Optional[CandidatePIIDTO] = None

class MatchRunResponse(BaseModel):
    run_id: str
    job_id: str
    job_title: str
    requested_count: int
    returned_count: int
    results: List[MatchResultItem]
    notice: Optional[str] = None  # explains if fewer than requested were available

# --- Resume Improvement Schemas ---

class SupportingEvidenceItem(BaseModel):
    source: str = "candidate_resume"
    text: str

class ResumeChangeItem(BaseModel):
    id: Optional[str] = None
    section: str = "general"
    target_element_id: Optional[str] = None
    original_text: str = ""
    proposed_text: str
    reason: str = ""
    supporting_evidence: List[SupportingEvidenceItem] = []
    requires_user_confirmation: bool = False
    status: str = "pending"  # "pending", "accepted", "rejected"

class ResumeGapItem(BaseModel):
    requirement: str
    status: str = "not_demonstrated"
    evidence: Optional[str] = None

class ResumeImprovementPlan(BaseModel):
    candidate_id: str
    target_job: str
    original_score: int = 0
    changes: List[ResumeChangeItem] = []
    gaps: List[ResumeGapItem] = []
    model_used: Optional[str] = None
    ikm_evidence_status: Optional[str] = None

class RecalculateScoreRequest(BaseModel):
    job_id: Optional[str] = None
    job_text: Optional[str] = None
    accepted_changes: List[Dict[str, Any]] = []

class RecalculateScoreResponse(BaseModel):
    original_score: int
    revised_score: int
    score_difference: int
    gained_requirements: List[str] = []
    remaining_gaps: List[str] = []
    explanation: str

class SuggestedRewrite(BaseModel):
    section: str
    current_evidence: str
    suggested_text: str
    requires_user_confirmation: bool = True
    rationale: str

class ImprovementResponse(BaseModel):
    doc_id: str
    job_id: Optional[str]
    job_title: Optional[str]
    internal_match_score: int
    score_disclaimer: str = (
        "Internal alignment score based on explicit evidence. "
        "Does not guarantee pass rate with external third-party ATS systems."
    )
    matched_requirements: List[MatchedRequirement]
    partially_demonstrated: List[Dict[str, Any]]
    not_demonstrated: List[MatchGap]
    formatting_issues: List[Dict[str, Any]]
    suggested_rewrites: List[SuggestedRewrite]
    original_text_preview: str
    improved_resume_text: Optional[str] = None
    change_summary: Optional[str] = None
    key_enhancements: Optional[List[str]] = None
    llm_model: Optional[str] = None
    changes: Optional[List[ResumeChangeItem]] = None
    gaps: Optional[List[ResumeGapItem]] = None
    candidate_name: Optional[str] = None
    candidate_personal_details: Optional[Dict[str, Any]] = None
    ikm_evidence_status: Optional[str] = None
    document_type: Optional[str] = None

class SaveVersionRequest(BaseModel):
    change_summary: str = Field(..., min_length=3)
    revised_content: str = Field(..., min_length=10)
    approved: bool = True
    candidate_name: Optional[str] = None
    candidate_role: Optional[str] = None
    candidate_phone: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_location: Optional[str] = None
    candidate_links: Optional[str] = None
    approved_changes: Optional[List[Dict[str, Any]]] = None

class ResumeVersionResponse(BaseModel):
    version_id: str
    doc_id: str
    parent_version_id: Optional[str] = None
    created_at: datetime
    created_by: str
    approved_by: Optional[str] = None
    change_summary: str
    dms_ref: str
    actual_score: Optional[int] = None
    score_breakdown: Optional[Dict[str, Any]] = None
    score_delta: Optional[int] = None
    score_explanation: Optional[str] = None

# --- Follow-Up & Workflow Schemas ---

class FollowUpItem(BaseModel):
    doc_id: str
    candidate_label: str
    full_name: Optional[str] = None
    status: str
    assigned_to: str
    last_action_at: Optional[datetime] = None
    last_action_type: str
    last_opened_at: Optional[datetime] = None
    days_inactive: int
    next_action_at: Optional[datetime] = None
    is_overdue: bool
    is_stale: bool = False
    notes: Optional[str] = None
    suggested_action: Optional[str] = None
    email_sent: bool = False
    email_sent_to: Optional[str] = None
    email_sent_at: Optional[datetime] = None
    pii: Optional[CandidatePIIDTO] = None

class NotificationItem(BaseModel):
    id: str
    doc_id: Optional[str] = None
    title: str
    message: str
    severity: str
    days_inactive: int
    created_at: Optional[str] = None
    is_read: bool = False
    email_sent: bool = False
    email_sent_to: Optional[str] = None
    email_sent_at: Optional[str] = None
    email_attachment_filename: Optional[str] = None

class EscalationEmailRequest(BaseModel):
    doc_id: str
    recipient: Optional[str] = "damayanthi.u@riscrm.com"
    reason: Optional[str] = None


class RecordActionRequest(BaseModel):
    action_type: str = Field(..., description="e.g. reviewed, contacted, shortlisted, rejected, snooze")
    status: Optional[str] = None
    notes: Optional[str] = None
    owner_id: Optional[str] = None
    next_action_at: Optional[datetime] = None

class DevelopmentPlanResponse(BaseModel):
    doc_id: str
    target_role: str
    skill_gaps: List[str]
    practical_projects: List[Dict[str, str]]
    learning_recommendations: List[Dict[str, str]]
    certifications: List[Dict[str, str]]
    recruiter_message_draft: str

# --- Dashboard Schemas ---

class DashboardSummaryResponse(BaseModel):
    total_resumes: int
    awaiting_review: int
    follow_ups_due: int
    overdue_count: int
    active_jobs: int
    top_skills_distribution: Dict[str, int]
    recent_activity: List[Dict[str, Any]]
    followup_status_distribution: Optional[Dict[str, int]] = None

# --- Bulk Delete Schemas ---

class BulkDeleteRequest(BaseModel):
    doc_ids: List[str]

class BulkDeleteResponse(BaseModel):
    success: bool
    deleted_count: int
    deleted_ids: List[str]
    failed_ids: List[Dict[str, str]]
    message: str
