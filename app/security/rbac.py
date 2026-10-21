from enum import Enum
from typing import List, Optional
from pydantic import BaseModel
from fastapi import HTTPException, Security, status, Header

class UserRole(str, Enum):
    RECRUITER = "recruiter"
    MANAGER = "recruitment_manager"
    ADMIN = "administrator"

class CurrentUser(BaseModel):
    user_id: str
    name: str
    role: UserRole
    tenant_id: str = "tenant-primary"

# Standard mock profiles for quick switching in UI
DEMO_USERS = {
    "recruiter-001": CurrentUser(
        user_id="recruiter-001",
        name="Jane Recruiter",
        role=UserRole.RECRUITER
    ),
    "manager-001": CurrentUser(
        user_id="manager-001",
        name="Marcus Vance (Manager)",
        role=UserRole.MANAGER
    ),
    "admin-001": CurrentUser(
        user_id="admin-001",
        name="Sarah Connor (Admin)",
        role=UserRole.ADMIN
    )
}

def get_current_user(
    x_user_id: Optional[str] = Header("recruiter-001", alias="X-User-Id")
) -> CurrentUser:
    """
    Extracts the authenticated user from the X-User-Id header or defaults to standard recruiter.
    """
    if x_user_id and x_user_id in DEMO_USERS:
        return DEMO_USERS[x_user_id]
    
    # Allow custom recruiter user ID
    return CurrentUser(
        user_id=x_user_id or "recruiter-001",
        name=f"User {x_user_id or 'recruiter-001'}",
        role=UserRole.RECRUITER
    )

def require_role(allowed_roles: List[UserRole]):
    def role_checker(user: CurrentUser = Security(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles and user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of the following roles: {[r.value for r in allowed_roles]}"
            )
        return user
    return role_checker
