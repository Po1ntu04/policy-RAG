"""Simple role-based authorization helpers."""

from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException, Request


def _normalize_roles(roles: Iterable[str]) -> set[str]:
    return {str(r).strip().lower() for r in roles if str(r).strip()}


def get_current_user(request: Request) -> dict | None:
    user = getattr(request.state, "user", None)
    return user if isinstance(user, dict) else None


def get_current_user_id(request: Request) -> str | None:
    user = get_current_user(request)
    if not user:
        return None
    return user.get("user_id")


def get_current_roles(request: Request) -> set[str]:
    user = get_current_user(request)
    if not user:
        return set()
    return _normalize_roles(user.get("roles") or [])


def require_roles(allowed_roles: Iterable[str]):
    allowed = _normalize_roles(allowed_roles)

    def _dependency(request: Request) -> bool:
        roles = get_current_roles(request)
        if not roles or not roles.intersection(allowed):
            raise HTTPException(status_code=403, detail="Forbidden")
        return True

    return _dependency


def disallow_roles(disallowed_roles: Iterable[str]):
    disallowed = _normalize_roles(disallowed_roles)

    def _dependency(request: Request) -> bool:
        roles = get_current_roles(request)
        if roles.intersection(disallowed):
            raise HTTPException(status_code=403, detail="Forbidden")
        return True

    return _dependency
