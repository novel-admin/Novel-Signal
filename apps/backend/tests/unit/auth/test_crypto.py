import pytest
from cryptography.fernet import Fernet
from novel_signal.config import Settings
from novel_signal.modules.auth.crypto import (
    CredentialEncryptionError,
    decrypt_credentials,
    encrypt_credentials,
)


def test_credentials_round_trip_without_exposing_plaintext() -> None:
    settings = Settings(source_encryption_key=Fernet.generate_key().decode())
    payload = {"client_id": "client", "refresh_token": "secret"}

    encrypted = encrypt_credentials(payload, settings)

    assert "secret" not in encrypted
    assert decrypt_credentials(encrypted, settings) == payload


def test_credentials_require_a_valid_key() -> None:
    with pytest.raises(CredentialEncryptionError):
        encrypt_credentials({"token": "secret"}, Settings())
