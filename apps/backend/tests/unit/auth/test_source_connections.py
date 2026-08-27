import pytest
from cryptography.fernet import Fernet
from novel_signal.config import Settings
from novel_signal.db import Base
from novel_signal.modules.auth.crypto import decrypt_credentials
from novel_signal.modules.auth.models import SourceCredential, User, Workspace
from novel_signal.sources.router import ConnectionWrite, save_connection
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def test_source_connection_stores_only_encrypted_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    settings = Settings(source_encryption_key=Fernet.generate_key().decode())
    monkeypatch.setattr("novel_signal.sources.router.get_settings", lambda: settings)

    with Session(engine) as session:
        user = User(email="owner@example.com", password_hash="hash")
        workspace = Workspace(name="Workspace")
        session.add_all([user, workspace])
        session.flush()
        result = save_connection(
            "amazon_ads",
            ConnectionWrite(
                account_identifiers={"profile_id": "profile-1"},
                scopes=["reports"],
                credentials={"refresh_token": "do-not-return"},
            ),
            workspace,
            session,
        )

        stored = session.query(SourceCredential).one()
        assert "do-not-return" not in stored.encrypted_payload
        assert decrypt_credentials(stored.encrypted_payload, settings) != {}
        assert result.provider == "amazon_ads"
        assert result.account_identifiers == {"profile_id": "profile-1"}
        assert not hasattr(result, "credentials")

    Base.metadata.drop_all(engine)
    engine.dispose()
