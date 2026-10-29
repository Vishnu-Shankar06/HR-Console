import hashlib
import shutil
from pathlib import Path
from typing import Tuple, Optional
from app.config import settings

class DMSAdapter:
    """
    Document Management System (DMS) Adapter.
    Interface for document checksum verification and reference resolution.
    Persistent documents and revisions are stored exclusively in IKM.
    """
    def __init__(self):
        pass

    def calculate_checksum(self, file_bytes: bytes) -> str:
        """Computes SHA-256 checksum for document verification and deduplication."""
        return hashlib.sha256(file_bytes).hexdigest()

    def store_original_file(self, doc_id: str, filename: str, content: bytes) -> Tuple[str, str]:
        """
        Computes document checksum and returns an immutable IKM reference.
        Zero local disk storage used.
        """
        checksum = self.calculate_checksum(content)
        dms_ref = f"ikm://{doc_id}"
        return dms_ref, checksum

    def store_version_file(self, version_id: str, content_str: str, file_type: str = "txt") -> str:
        """
        Returns an immutable IKM version reference.
        Zero local disk storage used.
        """
        return f"ikm://{version_id}"

    def get_file_path(self, dms_ref: str) -> Optional[Path]:
        """Resolves DMS reference path to absolute filesystem path if it is a local path."""
        if not dms_ref or dms_ref.startswith("ikm://") or dms_ref.startswith("http"):
            return None
        try:
            abs_path = settings.BASE_DIR / dms_ref
            if abs_path.exists():
                return abs_path
        except Exception:
            pass
        return None

dms_adapter = DMSAdapter()
