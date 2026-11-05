import time

import pytest
from fastapi.testclient import TestClient

from verityforge import auth


def test_disabled_when_unconfigured(monkeypatch):
    monkeypatch.delenv("VERITYFORGE_AUTH_SECRET", raising=False)
    monkeypatch.delenv("VERITYFORGE_USERS", raising=False)
    assert auth.auth_enabled() is False


def test_enabled_when_configured(monkeypatch):
    monkeypatch.setenv("VERITYFORGE_AUTH_SECRET", "s3cret")
    assert auth.auth_enabled() is True


def test_token_round_trip(monkeypatch):
    monkeypatch.setenv("VERITYFORGE_AUTH_SECRET", "s3cret")
    tok = auth.issue_token("alice")
    assert auth.verify_token(tok) == "alice"


def test_tampered_token_rejected(monkeypatch):
    monkeypatch.setenv("VERITYFORGE_AUTH_SECRET", "s3cret")
    tok = auth.issue_token("alice")
    body, sig = tok.split(".")
    forged = body + "." + ("A" * len(sig))
    with pytest.raises(auth.AuthError):
        auth.verify_token(forged)


def test_token_signed_with_other_secret_rejected(monkeypatch):
    monkeypatch.setenv("VERITYFORGE_AUTH_SECRET", "secret-A")
    tok = auth.issue_token("alice")
    monkeypatch.setenv("VERITYFORGE_AUTH_SECRET", "secret-B")  # key rotated / attacker's key
    with pytest.raises(auth.AuthError, match="bad signature"):
        auth.verify_token(tok)


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setenv("VERITYFORGE_AUTH_SECRET", "s3cret")
    tok = auth.issue_token("alice", ttl_s=-1)
    with pytest.raises(auth.AuthError, match="expired"):
        auth.verify_token(tok)


def test_authenticate_checks_credentials(monkeypatch):
    monkeypatch.setenv("VERITYFORGE_AUTH_SECRET", "s3cret")
    monkeypatch.setenv("VERITYFORGE_USERS", "alice:wonderland, bob:builder")
    assert auth.verify_token(auth.authenticate("alice", "wonderland")) == "alice"
    with pytest.raises(auth.AuthError):
        auth.authenticate("alice", "wrong")
    with pytest.raises(auth.AuthError):
        auth.authenticate("ghost", "x")


def _client():
    from verityforge.main import app
    return TestClient(app)


def test_api_open_when_auth_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("VERITYFORGE_AUTH_SECRET", raising=False)
    monkeypatch.delenv("VERITYFORGE_USERS", raising=False)
    c = _client()
    assert c.get("/api/v1/auth/status").json()["auth_enabled"] is False
    # a write route works without a token
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    r = c.post("/api/v1/tasks", json={"objective": "x", "workspace_root": str(tmp_path)})
    assert r.status_code == 202


def test_api_requires_token_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("VERITYFORGE_AUTH_SECRET", "s3cret")
    monkeypatch.setenv("VERITYFORGE_USERS", "alice:wonderland")
    c = _client()
    assert c.get("/api/v1/auth/status").json()["auth_enabled"] is True
    # GET stays open
    assert c.get("/api/v1/providers").status_code == 200
    # write route refused without a token
    r = c.post("/api/v1/tasks", json={"objective": "x", "workspace_root": str(tmp_path)})
    assert r.status_code == 401
    # login, then the write route works and the task is attributed to the user
    tok = c.post("/api/v1/auth/login", json={"username": "alice", "password": "wonderland"}).json()["token"]
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    r = c.post("/api/v1/tasks", json={"objective": "x", "workspace_root": str(tmp_path)},
               headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 202 and r.json()["scope"] == "standard"


def test_login_rejects_bad_password_when_enabled(monkeypatch):
    monkeypatch.setenv("VERITYFORGE_AUTH_SECRET", "s3cret")
    monkeypatch.setenv("VERITYFORGE_USERS", "alice:wonderland")
    c = _client()
    assert c.post("/api/v1/auth/login", json={"username": "alice", "password": "nope"}).status_code == 401
