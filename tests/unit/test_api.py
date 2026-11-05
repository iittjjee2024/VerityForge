from fastapi.testclient import TestClient

from verityforge.main import app

c = TestClient(app)


def test_health_and_verify_mock_is_labeled(monkeypatch):
    # Force mock mode regardless of any real keys in the ambient environment / .env.
    import verityforge.main as main
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(main, "_research_cache", {})
    assert c.get("/api/v1/health").status_code == 200
    r = c.post("/api/v1/verify", json={"answer": "Library X plan costs $19 per month."}).json()
    assert "mock" in r["research_provider"]
    assert r["claims"][0]["status"] == "Insufficient Evidence"  # empty mock corpus: not claimed false


def test_context_endpoint(tmp_path):
    (tmp_path / "a.py").write_text("def pagination_demo():\n    return 1\n")
    r = c.post("/api/v1/context", json={"workspace_root": str(tmp_path), "task": "fix pagination_demo"}).json()
    assert r["files"] == ["a.py"]
