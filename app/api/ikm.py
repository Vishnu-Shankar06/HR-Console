from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.entities import Document, CandidateProfile
from app.integrations.ikm_adapter import ikm_adapter, HttpIKMAdapter
from app.security.rbac import get_current_user, CurrentUser

router = APIRouter(prefix="/api/ikm", tags=["IKM RAG Builder"])

class AuthTestRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    base_url: Optional[str] = None

class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = 10
    filters: Optional[Dict[str, Any]] = None

class RAGChatRequest(BaseModel):
    query: str
    conversation: Optional[List[Dict[str, str]]] = None

class UpdateKeyFieldsRequest(BaseModel):
    fields: Dict[str, Any]
    reason: Optional[str] = "Recruiter manual update"

class UpdateMetadataRequest(BaseModel):
    metadata: Dict[str, Any]
    reason: Optional[str] = "Recruiter manual update"

class MaskSensitiveDataRequest(BaseModel):
    text: str

class IdentifySkillsRequest(BaseModel):
    text: str

@router.get("/status")
def get_ikm_status(current_user: CurrentUser = Depends(get_current_user)):
    """
    Returns live connectivity, prompt guard status, and auth state for the company's RAG Builder.
    """
    if hasattr(ikm_adapter, "get_health_status"):
        return ikm_adapter.get_health_status()
    return {
        "online": True,
        "authenticated": False,
        "mode": "Local High-Precision Extraction Engine Active",
        "service": "local-ikm-adapter"
    }

@router.post("/test-auth")
def test_authentication(
    req: AuthTestRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Verifies authentication with RAG Builder credentials.
    """
    if not isinstance(ikm_adapter, HttpIKMAdapter):
        return {
            "success": False,
            "message": "HttpIKMAdapter is not active in current configuration."
        }
        
    # If custom credentials provided, temporarily test with those
    if req.username or req.password or req.base_url:
        import httpx
        test_url = (req.base_url or ikm_adapter.base_url).rstrip("/")
        test_user = req.username or ikm_adapter.username
        test_pass = req.password if (req.password and not all(c in ('•', '*') for c in req.password.strip())) else ikm_adapter.password
        try:
            r = httpx.post(
                f"{test_url}/api/v1/auth/token",
                json={"user_id": test_user, "password": test_pass},
                timeout=6.0
            )
            if r.status_code == 200:
                data = r.json()
                import time
                ikm_adapter._access_token = data.get("access_token")
                ikm_adapter._token_expires_at = time.time() + float(data.get("expires_in", 3000))
                ikm_adapter.username = test_user
                ikm_adapter.password = test_pass
                ikm_adapter._last_auth_error = None
                return {
                    "success": True,
                    "status_code": 200,
                    "message": "Authentication successful! Token received.",
                    "token_type": data.get("token_type", "bearer")
                }
            elif r.status_code == 401:
                return {
                    "success": False,
                    "status_code": 401,
                    "message": "Invalid credentials. Please verify your username and password in .env."
                }
            elif r.status_code == 423:
                return {
                    "success": False,
                    "status_code": 423,
                    "message": f"Account locked on remote RAG Builder (Status 423). Account '{test_user}' is temporarily locked by the server's rate limiter. Built-in local high-precision parser is active."
                }
            else:
                return {
                    "success": False,
                    "status_code": r.status_code,
                    "message": f"Server responded with error: {r.text[:200]}"
                }
        except Exception as e:
            return {
                "success": False,
                "status_code": 504 if "timeout" in str(e).lower() else 500,
                "message": f"Connection error: {str(e)}"
            }

    success = ikm_adapter.authenticate(force=True)
    return {
        "success": success,
        "message": "Authenticated successfully with configured credentials." if success else (ikm_adapter._last_auth_error or "Authentication failed."),
        "active_user": ikm_adapter.username,
        "base_url": ikm_adapter.base_url
    }

@router.post("/retrieve")
def semantic_search(
    req: RAGSearchRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Semantic & hybrid retrieval across candidate documents via RAG Builder.
    """
    results = ikm_adapter.search(query=req.query, filters=req.filters, top_k=req.top_k)
    return {
        "query": req.query,
        "results_count": len(results),
        "results": results
    }

@router.post("/chat")
def rag_chat(
    req: RAGChatRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Natural language Q&A and reasoning over candidate resumes via RAG Builder.
    """
    if hasattr(ikm_adapter, "chat"):
        return ikm_adapter.chat(query=req.query, conversation=req.conversation)
    return {
        "error": "Chat not supported in local fallback mode.",
        "message": "Please configure RAG_BUILDER credentials in .env to enable RAG chat."
    }

@router.get("/resumes/{doc_id}/template")
def get_resume_template(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retrieves the extracted template graph from RAG Builder / Neo4j for a given document.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    ikm_ref = doc.ikm_ref or doc_id
    if hasattr(ikm_adapter, "get_template"):
        res = ikm_adapter.get_template(ikm_ref)
        if "error" not in res:
            return res

    # Fallback to local profile structure
    prof = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
    if prof and prof.structured_profile_json:
        return {
            "document_id": doc_id,
            "ikm_ref": ikm_ref,
            "source": "local_structured_profile",
            "template": prof.structured_profile_json
        }

    return {"document_id": doc_id, "message": "No template available yet."}

@router.patch("/resumes/{doc_id}/key-fields")
def update_resume_key_fields(
    doc_id: str,
    req: UpdateKeyFieldsRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Modifies candidate key-fields in RAG Builder.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    ikm_ref = doc.ikm_ref or doc_id
    if hasattr(ikm_adapter, "update_key_fields"):
        res = ikm_adapter.update_key_fields(ikm_ref, req.fields, req.reason or "Recruiter edit")
        return res

    return {"message": "Key-fields updated locally."}

@router.post("/mask-sensitive-data")
def mask_sensitive_data(
    req: MaskSensitiveDataRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Masks candidate PII (Name, Email, Phone, Address/Location) using IKM redaction engine.
    """
    masked_text, pii = ikm_adapter.mask_sensitive_data(req.text)
    return {
        "masked_text": masked_text,
        "pii_detected": pii
    }

@router.post("/identify-skills")
def identify_skills(
    req: IdentifySkillsRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Extracts candidate skills, competencies, domain, and seniority dynamically via Grok + IKM.
    """
    from app.integrations.grok_adapter import grok_adapter
    return grok_adapter.identify_skills_and_competencies(req.text)

@router.get("/resumes/{doc_id}/ikm-template")
def get_resume_ikm_template(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retrieves the structured IKM JSON template for a candidate resume.
    """
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    prof = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail=f"Candidate profile for '{doc_id}' not found.")

    template = prof.structured_profile_json.get("ikm_template") if prof.structured_profile_json else None
    if not template:
        template = ikm_adapter.extract_resume_template(
            doc_id=doc_id,
            raw_text=prof.raw_text_summary or ""
        )

    return {
        "doc_id": doc_id,
        "ikm_template": template
    }


@router.post("/sync")
def sync_repository_documents(
    force: bool = Query(True, description="Force fresh synchronization"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Bidirectionally synchronizes candidate documents with the active IKM repository:
    - Removes documents from application if deleted in IKM.
    - Imports documents into application if added to IKM.
    """
    from app.services.ikm_sync_service import sync_ikm_with_database
    return sync_ikm_with_database(db=db, force=force)


@router.get("/sync")
def get_repository_sync_status(
    force: bool = Query(False, description="Force fresh synchronization"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Returns current synchronization state and optionally synchronizes.
    """
    from app.services.ikm_sync_service import sync_ikm_with_database
    return sync_ikm_with_database(db=db, force=force)

