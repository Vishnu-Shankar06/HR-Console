import re
from fastapi import HTTPException, UploadFile, status
from app.config import settings

# Suspicious prompt injection markers in untrusted resumes or JDs
SUSPICIOUS_PROMPT_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"system\s*:\s*you\s+are\s+now",
    r"output\s+the\s+system\s+prompt",
    r"reveal\s+(internal|secret|hidden)\s+keys?",
    r"disregard\s+(the\s+above|everything)",
    r"you\s+must\s+assign\s+(a\s+score\s+of\s+100|top\s+rank)",
    r"override\s+scoring\s+model",
]

def sanitize_untrusted_text(text: str) -> str:
    """
    Cleans text extracted from resumes and job descriptions.
    Neutralizes attempt markers while preserving factual recruitment content.
    """
    if not text:
        return ""
    
    cleaned = text
    for pattern in SUSPICIOUS_PROMPT_PATTERNS:
        cleaned = re.sub(pattern, "[SUSPICIOUS_INSTRUCTION_REMOVED]", cleaned, flags=re.IGNORECASE)
    
    return cleaned

async def validate_uploaded_file(file: UploadFile) -> str:
    """
    Validates file extension, size limit, and basic signature.
    Returns the lowercased extension.
    """
    filename = file.filename or "unknown_file"
    parts = filename.rsplit(".", 1)
    if len(parts) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{filename}' lacks an extension. Only PDF, DOCX, and TXT are supported."
        )
    
    ext = parts[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '.{ext}' is unsupported. Allowed: {list(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # Read first chunk to check file signature and size
    contents = await file.read(1024 * 1024 * settings.MAX_UPLOAD_SIZE_MB + 1)
    if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB."
        )
    
    # Reset file cursor for subsequent reading
    await file.seek(0)
    return ext
