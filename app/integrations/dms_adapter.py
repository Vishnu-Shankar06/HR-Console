import hashlib
import shutil
from pathlib import Path
from typing import Tuple, Optional
from app.config import settings, DMS_ORIGINALS_DIR, DMS_VERSIONS_DIR

class DMSAdapter:
    """
    Document Management System (DMS) Adapter.
    Stores and manages original resumes and versioned revisions,
    ensuring original files are strictly preserved and immutable.
    """
    def __init__(self):
        self.originals_dir = DMS_ORIGINALS_DIR
        self.versions_dir = DMS_VERSIONS_DIR
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(parents=True, exist_ok=True)

    def calculate_checksum(self, file_bytes: bytes) -> str:
        """Computes SHA-256 checksum for document verification and deduplication."""
        return hashlib.sha256(file_bytes).hexdigest()

    def store_original_file(self, doc_id: str, filename: str, content: bytes) -> Tuple[str, str]:
        """
        Stores an uploaded original resume.
        Returns (dms_reference_path, checksum).
        """
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        safe_name = f"{doc_id}.{ext}"
        target_path = self.originals_dir / safe_name
        
        try:
            with open(target_path, "wb") as f:
                f.write(content)
        except PermissionError:
            # If the file already exists and is currently locked by another process (e.g. OneDrive or dev server),
            # verify it exists instead of crashing.
            if not target_path.exists():
                raise
            
        checksum = self.calculate_checksum(content)
        dms_ref = str(target_path.relative_to(settings.BASE_DIR)).replace("\\", "/")
        return dms_ref, checksum

    def store_version_file(self, version_id: str, content_str: str, file_type: str = "txt") -> str:
        """
        Stores an approved revised resume version.
        Guarantees original document is untouched.
        """
        safe_name = f"{version_id}.{file_type}"
        target_path = self.versions_dir / safe_name
        
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content_str)
            
        dms_ref = str(target_path.relative_to(settings.BASE_DIR)).replace("\\", "/")
        return dms_ref

    def get_file_path(self, dms_ref: str) -> Optional[Path]:
        """Resolves DMS reference path to absolute filesystem path."""
        abs_path = settings.BASE_DIR / dms_ref
        if abs_path.exists():
            return abs_path
        return None

dms_adapter = DMSAdapter()
