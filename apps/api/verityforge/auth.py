"""Authentication: signed stateless bearer tokens (HMAC-SHA256, stdlib only).

Design:
- Enforced in the backend via a FastAPI dependency, never in the UI.
- Tokens are signed with VERITYFORGE_AUTH_SECRET; they carry the user id and an expiry, and are tamper-evident.
- Users come from VERITYFORGE_USERS ("user:pass,user2:pass2"); passwords are compared in constant time.
- Dev/local fallback: if no secret AND no users are configured, auth is DISABLED and requests run as a local
  user. The moment either is set, auth is required. This never silently weakens a configured deployment.
- Read-only GETs stay open; state-changing routes require a valid token. Which routes are protected is decided
  in main.py, not here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time


class AuthError(Exception):
    pass


def _secret() -> bytes:
    return (os.getenv("VERITYFORGE_AUTH_SECRET") or "").encode()


def _users() -> dict[str, str]:
    raw = os.getenv("VERITYFORGE_USERS", "")
    out: dict[str, str] = {}
    for pair in raw.split(","):
        if ":" in pair:
            u, p = pair.split(":", 1)
            out[u.strip()] = p.strip()
    return out


def auth_enabled() -> bool:
    """Auth is active once a secret or a user list is configured. Default (neither) = disabled for local dev."""
    return bool(_secret() or _users())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(user_id: str, ttl_s: int = 86400) -> str:
    if not _secret():
        raise AuthError("VERITYFORGE_AUTH_SECRET not set; cannot issue tokens")
    payload = {"sub": user_id, "exp": int(time.time()) + ttl_s}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> str:
    """Return the user id for a valid, unexpired token, else raise AuthError."""
    if not _secret():
        raise AuthError("auth not configured")
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        raise AuthError("malformed token")
    expected = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):  # constant-time: no signature-forgery via timing
        raise AuthError("bad signature")
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        raise AuthError("bad payload")
    if payload.get("exp", 0) < time.time():
        raise AuthError("token expired")
    return payload["sub"]


def authenticate(username: str, password: str) -> str:
    """Validate credentials, return a token. Constant-time password compare."""
    users = _users()
    stored = users.get(username, "")
    ok = hmac.compare_digest(stored.encode(), password.encode()) and username in users
    if not ok:
        raise AuthError("invalid credentials")
    return issue_token(username)
