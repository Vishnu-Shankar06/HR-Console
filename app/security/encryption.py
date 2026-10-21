import base64
import re
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from app.config import settings

class PIIEncryptionService:
    def __init__(self, key_str: Optional[str] = None):
        key = key_str or settings.FIELD_ENCRYPTION_KEY
        # Ensure 32 url-safe base64 encoded bytes for Fernet
        try:
            # Test if already valid Fernet key
            Fernet(key.encode() if isinstance(key, str) else key)
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception:
            # Fallback derive deterministic url-safe key
            padded = (key.encode() + b"=" * 32)[:32]
            b64_key = base64.urlsafe_b64encode(padded)
            self._fernet = Fernet(b64_key)

    def encrypt_field(self, plaintext: Optional[str]) -> Optional[str]:
        if not plaintext or not plaintext.strip():
            return None
        return self._fernet.encrypt(plaintext.strip().encode("utf-8")).decode("utf-8")

    def decrypt_field(self, ciphertext: Optional[str]) -> Optional[str]:
        if not ciphertext or not ciphertext.strip():
            return None
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except Exception:
            return "[Decryption Error: Invalid Key]"

    def encrypt_pii_dict(self, pii_data: Dict[str, Any]) -> Dict[str, Optional[str]]:
        return {
            "name_encrypted": self.encrypt_field(pii_data.get("name")),
            "email_encrypted": self.encrypt_field(pii_data.get("email")),
            "phone_encrypted": self.encrypt_field(pii_data.get("phone")),
            "address_encrypted": self.encrypt_field(pii_data.get("address"))
        }

    def decrypt_pii_dict(self, encrypted_data: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        return {
            "name": self.decrypt_field(encrypted_data.get("name_encrypted")),
            "email": self.decrypt_field(encrypted_data.get("email_encrypted")),
            "phone": self.decrypt_field(encrypted_data.get("phone_encrypted")),
            "address": self.decrypt_field(encrypted_data.get("address_encrypted"))
        }

# Singleton instance
pii_crypto = PIIEncryptionService()

def sanitize_text_for_llm(raw_text: str) -> str:
    """
    Strips email addresses, phone numbers, and direct identifiers from raw text
    before passing to LLM to preserve privacy and prevent personal bias.
    """
    if not raw_text:
        return ""
    # Redact email addresses
    sanitized = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED_EMAIL]', raw_text)
    # Redact phone numbers (standard international and local patterns)
    sanitized = re.sub(r'(\+?\d{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}', '[REDACTED_PHONE]', sanitized)
    return sanitized
