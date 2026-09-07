"""Request-scoped tenant isolation.

Every tenant-owned row carries a denormalized ``workspace_id`` (see
``WorkspaceOwnedMixin``). Isolation has two layers:

1. Application layer (all databases): a request-scoped workspace ID stored in
   a :class:`contextvars.ContextVar` is applied automatically to every ORM
   session through SQLAlchemy events --
   ``before_insert`` backfills ``workspace_id`` on new rows and
   ``do_orm_execute`` adds ``with_loader_criteria`` filters to every ORM
   SELECT/UPDATE/DELETE, so a query that forgets an explicit workspace filter
   still cannot leak rows from another workspace.
2. Database layer (PostgreSQL): Row Level Security policies compare
   ``workspace_id`` to ``app.current_workspace_id``. ``after_begin`` issues
   ``SET LOCAL`` on every transaction while a scope is active, so direct
   PostgreSQL access is isolated even outside the ORM.

The middleware sets the scope after verifying membership; background workers
use :func:`tenant_scope` with the subject's workspace. Code without a scope
(CLI seeds, legacy fixtures, unconfigured dev) behaves exactly as before.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import String, event
from sqlalchemy.orm import (
    Session,
    mapped_column,
    with_loader_criteria,
)
from sqlalchemy.orm.base import Mapped

from novel_signal.db import Base

_current_workspace: ContextVar[str | None] = ContextVar(
    "novel_signal_workspace_id", default=None
)
_current_supabase_user: ContextVar[str | None] = ContextVar(
    "novel_signal_supabase_user_id", default=None
)


class WorkspaceOwnedMixin:
    """Denormalized tenant owner for every tenant-owned table.

    Plain ``String(36)`` identifier on purpose: no ``ForeignKey`` so collection
    metadata stays importable without the auth module and subset
    ``create_all`` calls in unit tests keep working. Indexes live in the
    migrations with per-table names (the metadata naming convention would
    otherwise collide across tables).
    """

    workspace_id: Mapped[str | None] = mapped_column(String(36))


_entities_cache: tuple[tuple[type[Any], ...], int] | None = None


def workspace_owned_entities() -> tuple[type[Any], ...]:
    """All mapped classes carrying tenant ownership (cached, self-invalidating)."""
    global _entities_cache
    mappers = list(Base.registry.mappers)
    if _entities_cache is not None and _entities_cache[1] == len(mappers):
        return _entities_cache[0]
    entities = tuple(
        mapper.class_
        for mapper in mappers
        if isinstance(mapper.class_, type) and issubclass(mapper.class_, WorkspaceOwnedMixin)
    )
    _entities_cache = (entities, len(mappers))
    return entities


def current_workspace_id() -> str | None:
    return _current_workspace.get()


@contextmanager
def tenant_scope(
    workspace_id: str | None, supabase_user_id: str | None = None
) -> Iterator[None]:
    """Run a block (request, worker job, CLI operation) as one workspace."""
    workspace_token = _current_workspace.set(str(workspace_id) if workspace_id else None)
    user_token = _current_supabase_user.set(supabase_user_id)
    try:
        yield
    finally:
        _current_workspace.reset(workspace_token)
        _current_supabase_user.reset(user_token)


def _fill_workspace_id(session: Session) -> None:
    workspace_id = _current_workspace.get()
    if not workspace_id:
        return
    for target in session.new:
        if isinstance(target, WorkspaceOwnedMixin) and target.workspace_id is None:
            target.workspace_id = workspace_id


def _apply_tenant_criteria(session: Session, statement: Any) -> Any:
    workspace_id = _current_workspace.get()
    if not workspace_id:
        return statement
    entities = workspace_owned_entities()
    if not entities:
        return statement
    options = [
        with_loader_criteria(
            entity,
            entity.workspace_id == workspace_id,
            include_aliases=True,
        )
        for entity in entities
    ]
    return statement.options(*options)


@event.listens_for(Session, "before_flush")
def _on_before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    _fill_workspace_id(session)


@event.listens_for(Session, "do_orm_execute")
def _on_do_orm_execute(execute_state: Any) -> None:
    if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        return
    if _current_workspace.get() is None:
        return
    execute_state.statement = _apply_tenant_criteria(
        execute_state.session, execute_state.statement
    )


@event.listens_for(Session, "after_begin")
def _on_after_begin(session: Session, transaction: Any, connection: Any) -> None:
    workspace_id = _current_workspace.get()
    if not workspace_id or connection.dialect.name != "postgresql":
        return
    try:
        connection.exec_driver_sql(
            "SELECT set_config('app.current_workspace_id', %s, TRUE)", (workspace_id,)
        )
        supabase_user_id = _current_supabase_user.get()
        if supabase_user_id:
            connection.exec_driver_sql(
                "SELECT set_config('app.current_supabase_user_id', %s, TRUE)",
                (supabase_user_id,),
            )
    except Exception:
        # RLS context must never break the request; the ORM criteria layer
        # still applies.
        pass


def orm_scoped_count() -> int:
    """Number of tenant-owned entities (used by tests)."""
    return len(workspace_owned_entities())


__all__ = [
    "WorkspaceOwnedMixin",
    "current_workspace_id",
    "orm_scoped_count",
    "tenant_scope",
    "workspace_owned_entities",
]
