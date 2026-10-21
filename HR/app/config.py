import os
from pathlib import Path
from cryptography.fernet import Fernet

BASE_DIR = Path(__file__).resolve().parent.parent

# Storage directories
STORAGE_DIR = BASE_DIR / "storage"
DMS_DIR = STORAGE_DIR / "dms"
DMS_ORIGINALS_DIR = DMS_DIR / "originals"
DMS_VERSIONS_DIR = DMS_DIR / "versions"
DB_DIR = STORAGE_DIR / "db"

# Ensure directories exist
DMS_ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
DMS_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

class Settings:
    BASE_DIR: Path = BASE_DIR
    APP_NAME: str = "AI Recruitment & Resume Intelligence Platform"
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() in ("true", "1")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DB_DIR / 'recruitment.db'}")
    
    # Cryptography / Field Encryption Key
    # In dev, auto-generate a stable key if not set
    _default_key = os.getenv("FIELD_ENCRYPTION_KEY")
    if not _default_key or len(_default_key) < 16:
        # Default dev key
        FIELD_ENCRYPTION_KEY: str = "dGhpcy1pcy1hLXNhbXBsZS0zMmJ5dGUtZW5jcnlwdGlvbi1rZXk="
    else:
        FIELD_ENCRYPTION_KEY: str = _default_key
        
    SECRET_KEY: str = os.getenv("SECRET_KEY", "recruitment-intelligence-app-secret-token-key-2026")
    
    # Workflow Configuration
    DEFAULT_MAX_SHORTLIST: int = int(os.getenv("DEFAULT_MAX_SHORTLIST", "50"))
    DEFAULT_INACTIVITY_THRESHOLD_DAYS: int = int(os.getenv("DEFAULT_INACTIVITY_THRESHOLD_DAYS", "7"))
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "15"))
    ALLOWED_EXTENSIONS: set = {"pdf", "docx", "doc", "txt"}
    
    # IKM / RAG Builder Config
    IKM_ENABLED: bool = os.getenv("IKM_ENABLED", "true").lower() in ("true", "1")
    RAG_BUILDER_BASE_URL: str = os.getenv("RAG_BUILDER_BASE_URL", os.getenv("IKM_BASE_URL", "http://16.113.145.53:8088")).rstrip("/")
    RAG_BUILDER_USERNAME: str = os.getenv("RAG_BUILDER_USERNAME", os.getenv("IKM_USERNAME", "resume-screening"))
    RAG_BUILDER_PASSWORD: str = os.getenv("RAG_BUILDER_PASSWORD", os.getenv("IKM_PASSWORD", "Rsd0ff0830976b2737033163fe27"))
    IKM_BASE_URL: str = RAG_BUILDER_BASE_URL
    IKM_USERNAME: str = RAG_BUILDER_USERNAME
    IKM_PASSWORD: str = RAG_BUILDER_PASSWORD
    IKM_API_KEY: str = os.getenv("IKM_API_KEY", "")
    IKM_REPOSITORY_ID: str = os.getenv("IKM_REPOSITORY_ID", "")
    IKM_TIMEOUT_SECONDS: float = float(os.getenv("IKM_TIMEOUT_SECONDS", "12.0"))
    
    # Neo4j Config
    NEO4J_ENABLED: bool = os.getenv("NEO4J_ENABLED", "false").lower() in ("true", "1")
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

    # LLM Config (Supports both xAI Grok and GroqCloud LPU)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "grok")
    GROK_API_KEY: str = os.getenv("GROK_API_KEY", os.getenv("GROQ_API_KEY", os.getenv("XAI_API_KEY", "")))
    
    _env_base_url = os.getenv("GROK_BASE_URL", os.getenv("GROQ_BASE_URL", os.getenv("LLM_BASE_URL", "")))
    if _env_base_url:
        GROK_BASE_URL: str = _env_base_url
    elif LLM_PROVIDER.lower() in ("groq", "groqcloud") or GROK_API_KEY.startswith("gsk_"):
        GROK_BASE_URL: str = "https://api.groq.com/openai/v1"
    elif LLM_PROVIDER.lower() in ("openai",) or GROK_API_KEY.startswith("sk-"):
        GROK_BASE_URL: str = "https://api.openai.com/v1"
    else:
        GROK_BASE_URL: str = "https://api.x.ai/v1"

    _env_model = os.getenv("GROK_MODEL", os.getenv("GROQ_MODEL", os.getenv("LLM_MODEL", "")))
    if _env_model:
        GROK_MODEL: str = _env_model
    elif "groq.com" in GROK_BASE_URL:
        GROK_MODEL: str = "llama-3.3-70b-versatile"
    elif "openai.com" in GROK_BASE_URL:
        GROK_MODEL: str = "gpt-4o"
    else:
        GROK_MODEL: str = "grok-2-latest"

settings = Settings()
