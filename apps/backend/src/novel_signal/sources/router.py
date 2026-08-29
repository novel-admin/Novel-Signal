from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.api.dependencies import WorkspaceDep
from novel_signal.config import get_settings
from novel_signal.db import get_db
from novel_signal.modules.auth.crypto import encrypt_credentials
from novel_signal.modules.auth.models import SourceConnection, SourceCredential
from novel_signal.sources.base import SourceType
from novel_signal.sources.registry import source_definitions

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceStatus(BaseModel):
    source_type: SourceType
    owner: str
    purpose: str
    configured: bool


class ConnectionRead(BaseModel):
    id: str
    provider: str
    status: str
    account_identifiers: dict[str, object] | None
    scopes: list[str] | None
    last_verified_at: datetime | None
    last_sync_at: datetime | None
    error_summary: str | None


class ConnectionWrite(BaseModel):
    account_identifiers: dict[str, object] = Field(default_factory=dict)
    scopes: list[str] = Field(default_factory=list, max_length=20)
    credentials: dict[str, str] = Field(default_factory=dict)


SUPPORTED_CONNECTIONS = {
    "amazon_sp",
    "amazon_ads",
    "google_ads",
    "meta_ads",
    "amazon_public",
}


def _connection_or_404(provider: str) -> None:
    if provider not in SUPPORTED_CONNECTIONS:
        raise HTTPException(
            status_code=422,
            detail={"code": "unsupported_provider", "provider": provider},
        )


@router.get("", response_model=list[SourceStatus])
def list_sources() -> list[SourceStatus]:
    return [SourceStatus(**definition.__dict__) for definition in source_definitions()]


@router.get("/connections", response_model=list[ConnectionRead])
def list_connections(
    workspace: WorkspaceDep, session: Annotated[Session, Depends(get_db)]
) -> list[ConnectionRead]:
    connections = session.scalars(
        select(SourceConnection)
        .where(SourceConnection.workspace_id == workspace.id)
        .order_by(SourceConnection.provider)
    )
    return [ConnectionRead.model_validate(item, from_attributes=True) for item in connections]


@router.put("/connections/{provider}", response_model=ConnectionRead)
def save_connection(
    provider: str,
    payload: ConnectionWrite,
    workspace: WorkspaceDep,
    session: Annotated[Session, Depends(get_db)],
) -> ConnectionRead:
    _connection_or_404(provider)
    if not payload.credentials:
        raise HTTPException(status_code=422, detail={"code": "credentials_required"})
    connection = session.scalar(
        select(SourceConnection).where(
            SourceConnection.workspace_id == workspace.id,
            SourceConnection.provider == provider,
        )
    )
    if connection is None:
        connection = SourceConnection(workspace_id=workspace.id, provider=provider)
        session.add(connection)
        session.flush()
    credential = session.scalar(
        select(SourceCredential).where(SourceCredential.connection_id == connection.id)
    )
    encrypted = encrypt_credentials(payload.credentials, get_settings())
    if credential is None:
        credential = SourceCredential(connection_id=connection.id, encrypted_payload=encrypted)
        session.add(credential)
    else:
        credential.encrypted_payload = encrypted
        credential.key_version = get_settings().source_encryption_key_version
    connection.account_identifiers = payload.account_identifiers
    connection.scopes = payload.scopes
    connection.status = "configured"
    connection.error_summary = None
    connection.updated_at = datetime.now(UTC)
    session.commit()
    return ConnectionRead.model_validate(connection, from_attributes=True)


@router.delete("/connections/{provider}", status_code=204)
def delete_connection(
    provider: str,
    workspace: WorkspaceDep,
    session: Annotated[Session, Depends(get_db)],
) -> None:
    _connection_or_404(provider)
    connection = session.scalar(
        select(SourceConnection).where(
            SourceConnection.workspace_id == workspace.id,
            SourceConnection.provider == provider,
        )
    )
    if connection is not None:
        session.delete(connection)
        session.commit()
