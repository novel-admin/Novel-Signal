"""Supabase-only auth mapping, roles, audit log, and workspace RLS.

Revision ID: 20260829_01
Revises: 20260828_01

- users.supabase_user_id (auth.users.id mapping), password_hash nullable.
- workspace_members role defaults to viewer; legacy 'member' -> 'viewer'.
- auth_audit_events append-only table (no secrets).
- collection_jobs.workspace_id + raw_evidence.workspace_id for tenant isolation.
- PostgreSQL Row Level Security as a second isolation layer for
  workspaces, workspace_members, source_connections, source_credentials
  (via connection), collection_jobs, raw_evidence, and auth_audit_events.
  Domain tables without a workspace_id remain single-workspace in this
  private deployment and are gated at the API layer by active membership;
  see docs/auth/supabase.md for the ownership path and follow-up.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_01"
down_revision: str = "20260828_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    "workspaces",
    "workspace_members",
    "source_connections",
    "source_credentials",
    "collection_jobs",
    "raw_evidence",
    "auth_audit_events",
]


def upgrade() -> None:
    # Users: Supabase mapping, no application passwords for production auth.
    op.add_column("users", sa.Column("supabase_user_id", sa.String(length=36), nullable=True))
    op.create_index("ix_users_supabase_user_id", "users", ["supabase_user_id"], unique=True)
    op.create_unique_constraint(
        "uq_users_supabase_user_id", "users", ["supabase_user_id"]
    )
    with op.batch_alter_table("users", recreate="never") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=True)

    # Roles: owner/admin/analyst/viewer. Migrate legacy values.
    op.execute("UPDATE workspace_members SET role='viewer' WHERE role='member'")
    op.execute(
        "UPDATE workspace_members SET role='viewer' "
        "WHERE role NOT IN ('owner','admin','analyst','viewer')"
    )
    with op.batch_alter_table("workspace_members", recreate="never") as batch:
        batch.alter_column(
            "role", existing_type=sa.String(length=30), server_default="viewer"
        )
    op.create_check_constraint(
        "ck_workspace_members_valid_role",
        "workspace_members",
        "role IN ('owner','admin','analyst','viewer')",
    )

    op.create_table(
        "auth_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("supabase_user_id", sa.String(length=36), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_audit_events_event_type", "auth_audit_events", ["event_type"])
    op.create_index(
        "ix_auth_audit_events_supabase_user_id", "auth_audit_events", ["supabase_user_id"]
    )
    op.create_index("ix_auth_audit_events_workspace_id", "auth_audit_events", ["workspace_id"])

    # Workspace ownership for collection Еффесtive isolation.
    op.add_column(
        "collection_jobs",
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_collection_jobs_workspace_id", "collection_jobs", ["workspace_id"])
    op.add_column(
        "raw_evidence",
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_raw_evidence_workspace_id", "raw_evidence", ["workspace_id"])

    # RLS second layer (PostgreSQL only; SQLite skips these statements).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION app_current_workspace_id() RETURNS TEXT AS $$
              SELECT NULLIF(current_setting('app.current_workspace_id', TRUE), '');
            $$ LANGUAGE SQL STABLE;
            """
        )
        # workspaces: member can read their workspace; writes via owner/admin API only.
        op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS workspaces_member_read ON workspaces;")
        op.execute(
            """
            CREATE POLICY workspaces_member_read ON workspaces FOR SELECT
              USING (id::TEXT = app_current_workspace_id());
            """
        )
        op.execute("DROP POLICY IF EXISTS workspaces_member_write ON workspaces;")
        op.execute(
            """
            CREATE POLICY workspaces_member_write ON workspaces FOR ALL
              USING (id::TEXT = app_current_workspace_id())
              WITH CHECK (id::TEXT = app_current_workspace_id());
            """
        )
        op.execute("ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS workspace_members_isolation ON workspace_members;")
        op.execute(
            """
            CREATE POLICY workspace_members_isolation ON workspace_members FOR ALL
              USING (workspace_id::TEXT = app_current_workspace_id())
              WITH CHECK (workspace_id::TEXT = app_current_workspace_id());
            """
        )
        op.execute("ALTER TABLE source_connections ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS source_connections_isolation ON source_connections;")
        op.execute(
            """
            CREATE POLICY source_connections_isolation ON source_connections FOR ALL
              USING (workspace_id::TEXT = app_current_workspace_id())
              WITH CHECK (workspace_id::TEXT = app_current_workspace_id());
            """
        )
        op.execute("ALTER TABLE source_credentials ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS source_credentials_isolation ON source_credentials;")
        op.execute(
            """
            CREATE POLICY source_credentials_isolation ON source_credentials FOR ALL
              USING (EXISTS (
                SELECT 1 FROM source_connections c
                WHERE c.id::TEXT = source_credentials.connection_id::TEXT
                  AND c.workspace_id::TEXT = app_current_workspace_id()
              ))
              WITH CHECK (EXISTS (
                SELECT 1 FROM source_connections c
                WHERE c.id::TEXT = source_credentials.connection_id::TEXT
                  AND c.workspace_id::TEXT = app_current_workspace_id()
              ));
            """
        )
        op.execute("ALTER TABLE collection_jobs ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS collection_jobs_isolation ON collection_jobs;")
        op.execute(
            """
            CREATE POLICY collection_jobs_isolation ON collection_jobs FOR ALL
              USING (workspace_id IS NULL OR workspace_id::TEXT = app_current_workspace_id())
              WITH CHECK (workspace_id::TEXT = app_current_workspace_id());
            """
        )
        op.execute("ALTER TABLE raw_evidence ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS raw_evidence_isolation ON raw_evidence;")
        op.execute(
            """
            CREATE POLICY raw_evidence_isolation ON raw_evidence FOR ALL
              USING (workspace_id IS NULL OR workspace_id::TEXT = app_current_workspace_id())
              WITH CHECK (workspace_id::TEXT = app_current_workspace_id());
            """
        )
        op.execute("ALTER TABLE auth_audit_events ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS auth_audit_events_isolation ON auth_audit_events;")
        op.execute(
            """
            CREATE POLICY auth_audit_events_isolation ON auth_audit_events FOR ALL
              USING (workspace_id IS NULL OR workspace_id::TEXT = app_current_workspace_id())
              WITH CHECK (workspace_id IS NULL OR workspace_id::TEXT = app_current_workspace_id());
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS auth_audit_events_isolation ON auth_audit_events;")
        op.execute("ALTER TABLE auth_audit_events DISABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS raw_evidence_isolation ON raw_evidence;")
        op.execute("ALTER TABLE raw_evidence DISABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS collection_jobs_isolation ON collection_jobs;")
        op.execute("ALTER TABLE collection_jobs DISABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS source_credentials_isolation ON source_credentials;")
        op.execute("ALTER TABLE source_credentials DISABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS source_connections_isolation ON source_connections;")
        op.execute("ALTER TABLE source_connections DISABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS workspace_members_isolation ON workspace_members;")
        op.execute("ALTER TABLE workspace_members DISABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS workspaces_member_write ON workspaces;")
        op.execute("DROP POLICY IF EXISTS workspaces_member_read ON workspaces;")
        op.execute("ALTER TABLE workspaces DISABLE ROW LEVEL SECURITY;")
        op.execute("DROP FUNCTION IF EXISTS app_current_workspace_id();")

    op.drop_index("ix_raw_evidence_workspace_id", table_name="raw_evidence")
    op.drop_column("raw_evidence", "workspace_id")
    op.drop_index("ix_collection_jobs_workspace_id", table_name="collection_jobs")
    op.drop_column("collection_jobs", "workspace_id")

    op.drop_index("ix_auth_audit_events_workspace_id", table_name="auth_audit_events")
    op.drop_index("ix_auth_audit_events_supabase_user_id", table_name="auth_audit_events")
    op.drop_index("ix_auth_audit_events_event_type", table_name="auth_audit_events")
    op.drop_table("auth_audit_events")

    op.drop_constraint("ck_workspace_members_valid_role", "workspace_members", type_="check")
    with op.batch_alter_table("workspace_members", recreate="never") as batch:
        batch.alter_column(
            "role", existing_type=sa.String(length=30), server_default="member"
        )
    op.drop_constraint("uq_users_supabase_user_id", "users", type_="unique")
    op.drop_index("ix_users_supabase_user_id", table_name="users")
    op.drop_column("users", "supabase_user_id")
    with op.batch_alter_table("users", recreate="never") as batch:
        batch.alter_column(
            "password_hash", existing_type=sa.String(length=255), nullable=False
        )
