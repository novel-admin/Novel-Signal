from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from novel_signal.config import Settings, get_settings


class CredentialEncryptionError(ValueError):
    """Raised when source credentials cannot be encrypted or decrypted safely."""


def _fernet(settings: Settings) -> Fernet:
    key = settings.source_encryption_key.get_secret_value()
    if not key:
        raise CredentialEncryptionError("Source encryption key is not configured")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as error:
        raise CredentialEncryptionError("Source encryption key is invalid") from error


def encrypt_credentials(payload: dict[str, str], settings: Settings | None = None) -> str:
    current = settings or get_settings()
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return _fernet(current).encrypt(encoded).decode()


def decrypt_credentials(value: str, settings: Settings | None = None) -> dict[str, str]:
    current = settings or get_settings()
    try:
        payload = json.loads(_fernet(current).decrypt(value.encode()))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise CredentialEncryptionError("Source credentials could not be decrypted") from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in payload.items()
    ):
        raise CredentialEncryptionError("Source credential payload is invalid")
    return payload
