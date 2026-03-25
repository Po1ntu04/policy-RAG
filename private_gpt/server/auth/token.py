"""HMAC-based access token helpers (stateless)."""

from __future__ import annotations

import base64
import hmac
import hashlib
import json
import time
from typing import Any


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(payload: dict[str, Any], secret: str, expires_in: int = 7200) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    body = {
        **payload,
        "iat": now,
        "exp": now + int(expires_in),
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    body_b64 = _b64url_encode(json.dumps(body, separators=(",", ":")).encode())
    message = f"{header_b64}.{body_b64}".encode()
    signature = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{body_b64}.{sig_b64}"


def verify_token(token: str, secret: str) -> dict[str, Any] | None:
    try:
        header_b64, body_b64, sig_b64 = token.split(".")
    except ValueError:
        return None
    message = f"{header_b64}.{body_b64}".encode()
    expected_sig = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_encode(expected_sig), sig_b64):
        return None
    body = json.loads(_b64url_decode(body_b64))
    exp = int(body.get("exp", 0))
    if exp and exp < int(time.time()):
        return None
    return body
