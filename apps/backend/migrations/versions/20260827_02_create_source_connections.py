"""Add workspace-owned source connection metadata and encrypted credentials."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260827_02"
down_revision = "20260827_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="configured", nullable=False),
        sa.Column("account_identifiers", sa.JSON(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "provider", name="uq_source_connections_workspace_provider"
        ),
    )
    op.create_index("ix_source_connections_workspace_id", "source_connections", ["workspace_id"])
    op.create_table(
        "source_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["connection_id"], ["source_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id"),
    )
    op.create_index("ix_source_credentials_connection_id", "source_credentials", ["connection_id"])


def downgrade() -> None:
    op.drop_index("ix_source_credentials_connection_id", table_name="source_credentials")
    op.drop_table("source_credentials")
    op.drop_index("ix_source_connections_workspace_id", table_name="source_connections")
    op.drop_table("source_connections")
