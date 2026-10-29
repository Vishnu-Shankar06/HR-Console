import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.models.database import Base, get_db
from app.models.seed import seed_database_if_empty
from app.main import app

from sqlalchemy.pool import StaticPool

TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return engine

@pytest.fixture(scope="function")
def db_session(engine):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    seed_database_if_empty(session)
    yield session
    session.close()

@pytest.fixture(scope="function")
def client(db_session):
    from app.services.resume_preview_service import resume_preview_service
    from app.integrations.ikm_adapter import ikm_adapter
    resume_preview_service.invalidate_cache()
    if hasattr(ikm_adapter, "invalidate_cache"):
        ikm_adapter.invalidate_cache()
    if hasattr(ikm_adapter, "_download_cache"):
        ikm_adapter._download_cache.clear()
    # Re-seed cache with genuine sample resume bytes
    from app.models.seed import seed_database_if_empty
    seed_database_if_empty(db_session)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    resume_preview_service.invalidate_cache()
    if hasattr(ikm_adapter, "invalidate_cache"):
        ikm_adapter.invalidate_cache()
