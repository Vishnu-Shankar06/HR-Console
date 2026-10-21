import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, BASE_DIR
from app.models.database import engine, Base, SessionLocal
from app.models.seed import seed_database_if_empty
from app.api.resumes import router as resumes_router
from app.api.jobs import router as jobs_router
from app.api.matching import router as matching_router
from app.api.improvements import router as improvements_router
from app.api.followups import router as followups_router
from app.api.dashboard import router as dashboard_router
from app.api.audit import router as audit_router
from app.api.ikm import router as ikm_router
from app.integrations.ikm_adapter import ikm_adapter

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    Base.metadata.create_all(bind=engine)
    # Seed initial test data
    db = SessionLocal()
    try:
        seed_database_if_empty(db)
    finally:
        db.close()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="Digital recruitment intelligence platform for candidate matching, resume improvement, and follow-up management.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global safe error handling
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Return friendly error without leaking internal secrets or raw stack traces
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal processing error occurred. Please verify your inputs or retry."}
    )

# Register API Routers
app.include_router(resumes_router)
app.include_router(jobs_router)
app.include_router(matching_router)
app.include_router(improvements_router)
app.include_router(followups_router)
app.include_router(dashboard_router)
app.include_router(audit_router)
app.include_router(ikm_router)

# Health & Status Endpoint
@app.get("/api/health", tags=["Health"])
def health_check():
    ikm_health = ikm_adapter.get_health_status() if hasattr(ikm_adapter, "get_health_status") else {"online": True, "active_mode": "Local"}
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "ikm_mode": ikm_health.get("active_mode", "Enterprise RAG Engine"),
        "ikm_rag_builder": {
            "enabled": settings.IKM_ENABLED,
            "base_url": settings.RAG_BUILDER_BASE_URL,
            "username": settings.RAG_BUILDER_USERNAME,
            "online": ikm_health.get("online", False),
            "authenticated": ikm_health.get("authenticated", False),
            "active_mode": ikm_health.get("active_mode", "Local Engine"),
            "prompt_guard": ikm_health.get("prompt_guard")
        },
        "graph_mode": "Neo4j Active" if settings.NEO4J_ENABLED else "In-Memory Graph Engine",
        "field_encryption": "Authenticated AES/Fernet Enabled"
    }

# Mount Frontend
frontend_dir = BASE_DIR / "frontend"
frontend_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

@app.get("/")
def serve_index():
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": f"Welcome to {settings.APP_NAME}. Frontend is loading."}
