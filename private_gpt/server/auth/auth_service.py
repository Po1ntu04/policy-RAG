"""Authentication service backed by Postgres."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any

from private_gpt.server.auth.token import create_token
from private_gpt.server.db.postgres import auto_migrate, get_connection
from private_gpt.settings.settings import settings

logger = logging.getLogger(__name__)


def _pbkdf2_hash(password: str, salt: str, iterations: int) -> str:
    salt_bytes = base64.urlsafe_b64decode(salt + "==")
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, iterations)
    return base64.urlsafe_b64encode(dk).decode().rstrip("=")


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iter_str, salt, hashed = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        computed = _pbkdf2_hash(password, salt, iterations)
        return hmac.compare_digest(computed, hashed)
    except Exception:
        return False


class AuthService:
    def __init__(self) -> None:
        auto_migrate()

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, username, display_name, password_hash, status
                    FROM app_users
                    WHERE username = %s
                    """,
                    (username,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                columns = [d[0] for d in cur.description]
        return dict(zip(columns, row))

    def get_roles(self, user_id: str) -> list[str]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.role_name
                    FROM user_roles ur
                    JOIN roles r ON r.role_id = ur.role_id
                    WHERE ur.user_id = %s
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
        return [row[0] for row in rows]

    def authenticate(self, username: str, password: str) -> tuple[dict[str, Any] | None, list[str]]:
        user = self.get_user_by_username(username)
        if not user:
            return None, []
        if user.get("status") != "active":
            return None, []
        if not verify_password(password, user.get("password_hash") or ""):
            return None, []
        roles = self.get_roles(str(user["user_id"]))
        return user, roles

    def issue_token(self, user: dict[str, Any], roles: list[str]) -> str:
        payload = {
            "user_id": str(user["user_id"]),
            "username": user["username"],
            "display_name": user.get("display_name"),
            "roles": roles,
        }
        secret = settings().server.auth.secret
        return create_token(payload, secret, expires_in=7200)
