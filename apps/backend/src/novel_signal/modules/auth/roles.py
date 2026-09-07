"""Workspace roles and permissions.

Roles (least to most privilege): viewer < analyst < admin < owner.

- viewer: read-only access.
- analyst: manage products, competitors, keywords, proposals, battle cards,
  gaps, and actions.
- admin: manage workspace data, products, competitors, collection jobs,
  source connections, and actions.
- owner: full workspace access and role/membership administration.
"""

from __future__ import annotations

from typing import Literal

Role = Literal["owner", "admin", "analyst", "viewer"]

ROLE_RANK: dict[str, int] = {"viewer": 1, "analyst": 2, "admin": 3, "owner": 4}

VALID_ROLES: tuple[str, ...] = ("owner", "admin", "analyst", "viewer")

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def normalize_role(role: str | None) -> str | None:
    if role is None:
        return None
    candidate = role.strip().lower()
    if candidate == "member":  # legacy default before Supabase roles
        return "viewer"
    return candidate if candidate in ROLE_RANK else None


def meets_requirement(role: str, minimum: Role) -> bool:
    normalized = normalize_role(role)
    if normalized is None:
        return False
    return ROLE_RANK[normalized] >= ROLE_RANK[minimum]


def can_write(role: str) -> bool:
    """Viewers are read-only; analyst and above may write."""
    return meets_requirement(role, "analyst")


def can_manage_workspace(role: str) -> bool:
    return meets_requirement(role, "admin")


def can_manage_members(role: str) -> bool:
    return meets_requirement(role, "owner")


def can_change_role(actor_role: str, target_current_role: str | None, new_role: Role) -> bool:
    """Only owners/admins may change membership; owners alone grant owner."""
    actor = normalize_role(actor_role)
    if actor is None or new_role not in ROLE_RANK:
        return False
    if actor == "owner":
        return True
    if actor == "admin":
        # Admins may manage analyst/viewer but cannot grant admin/owner
        # and cannot modify an owner.
        if target_current_role is not None and normalize_role(target_current_role) == "owner":
            return False
        return new_role in {"analyst", "viewer"}
    return False


__all__ = [
    "Role",
    "ROLE_RANK",
    "VALID_ROLES",
    "WRITE_METHODS",
    "can_change_role",
    "can_manage_members",
    "can_manage_workspace",
    "can_write",
    "meets_requirement",
    "normalize_role",
]
