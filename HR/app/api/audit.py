from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.models.database import get_db
from app.models.entities import AuditEvent
from app.security.rbac import get_current_user, CurrentUser

router = APIRouter(prefix="/api/audit", tags=["Audit & Security"])

class AuditEventDTO(BaseModel):
    event_id: str
    actor_id: str
    action: str
    target_doc_id: Optional[str] = None
    timestamp: datetime
    outcome: str
    metadata: Optional[dict] = None

@router.get("/events", response_model=List[AuditEventDTO])
def get_audit_events(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Returns security audit log events:
    PII access, original resume downloads, candidate match runs, document versions.
    """
    events = (
        db.query(AuditEvent)
        .order_by(AuditEvent.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        AuditEventDTO(
            event_id=e.event_id,
            actor_id=e.actor_id,
            action=e.action,
            target_doc_id=e.target_doc_id,
            timestamp=e.timestamp,
            outcome=e.outcome,
            metadata=e.metadata_json
        )
        for e in events
    ]
