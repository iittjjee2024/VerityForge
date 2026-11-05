"""Authentication: signed stateless bearer tokens (HMAC-SHA256, stdlib only).

Design:
- Enforced in the backend via a FastAPI dependency, never in the UI.
- Tokens are signed with VERITYFORGE_AUTH_SECRET; they carry the user id and an expiry, and are tamper-evident.
- Users come from VERITYFORGE_USERS ("user:hash,user2:hash2"). Passwords are stored as PBKDF2-HMAC-SHA256
  hashes (self-describing: pbkdf2_sha256$iters$salt$hash). Legacy plaintext entries still work but are
  discouraged; generate hashes with `python apps/cli/hash_password.py`. Verification is constant-time.
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


_PBKDF2_ITERATIONS = 200_000  # OWASP-aligned work factor for PBKDF2-HMAC-SHA256
_HASH_PREFIX = "pbkdf2_sha256$"
# A fixed dummy hash so authenticate() does equal work for unknown users (mitigates username enumeration by timing).
_DUMMY_HASH = _HASH_PREFIX + f"{_PBKDF2_ITERATIONS}$" + _b64(b"0" * 16) + "$" + _b64(b"0" * 32)


def hash_password(password: str, *, iterations: int = _PBKDF2_ITERATIONS, salt: bytes | None = None) -> str:
    """Return a self-describing PBKDF2-HMAC-SHA256 hash: pbkdf2_sha256$<iters>$<salt>$<hash>."""
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{_HASH_PREFIX}{iterations}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification. Accepts a PBKDF2 hash, or (legacy) a plaintext value for backward compat."""
    if stored.startswith(_HASH_PREFIX):
        try:
            _, iters, salt_b64, hash_b64 = stored.split("$", 3)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt_b64), int(iters))
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(_b64(dk), hash_b64)
    # Legacy plaintext entry (pre-hashing configs). Still constant-time; a warning is surfaced by stored_is_hashed().
    return hmac.compare_digest(stored.encode(), password.encode())


def stored_is_hashed(stored: str) -> bool:
    return stored.startswith(_HASH_PREFIX)


def authenticate(username: str, password: str) -> str:
    """Validate credentials, return a token. Hashes are PBKDF2; verification is constant-time and does equal
    work for unknown users to avoid leaking which usernames exist."""
    users = _users()
    stored = users.get(username)
    if stored is None:
        verify_password(password, _DUMMY_HASH)  # waste equivalent time, then fail
        raise AuthError("invalid credentials")
    if not verify_password(password, stored):
        raise AuthError("invalid credentials")
    return issue_token(username)
