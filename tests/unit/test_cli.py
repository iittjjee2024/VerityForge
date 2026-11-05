"""CLI tests. The CLI is a thin httpx client; we point httpx at the real FastAPI app via ASGITransport,
so the actual endpoints run in-process (no network, no live server)."""
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

CLI_PATH = Path(__file__).resolve().parents[2] / "apps" / "cli" / "verityforge_cli.py"
spec = importlib.util.spec_from_file_location("vf_cli", CLI_PATH)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

from verityforge.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def route_httpx_to_app(monkeypatch):
    from fastapi.testclient import TestClient
    client = TestClient(app)

    def fake_request(method, url, **kw):
        kw.pop("timeout", None)
        path = "/api/v1" + url.split("/api/v1", 1)[1]
        return client.request(method, path, **kw)

    monkeypatch.setattr(httpx, "request", fake_request)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    import verityforge.main as main
    monkeypatch.setattr(main, "_research_cache", {})
    yield


def run(args, capsys):
    code = cli.main(args)
    return code, capsys.readouterr().out


def test_health(capsys):
    code, out = run(["health"], capsys)
    assert code == 0 and "status: ok" in out


def test_verify_outputs_claims(capsys):
    code, out = run(["verify", "Library X plan costs $19 per month."], capsys)
    assert code == 0 and "Insufficient Evidence" in out  # mock research, empty corpus


def test_context_reports_savings(tmp_path, capsys):
    (tmp_path / "pager.py").write_text("def paginate(items, size):\n    return items[:size]\n")
    code, out = run(["context", str(tmp_path), "fix paginate"], capsys)
    assert code == 0 and "pager.py" in out and "saved" in out


def test_json_flag_emits_json(capsys):
    code, out = run(["--json", "health"], capsys)
    import json
    assert code == 0 and json.loads(out)["status"] == "ok"


def test_approvals_empty(capsys):
    code, out = run(["approvals"], capsys)
    assert code == 0 and "no pending approvals" in out


def test_unknown_task_status_errors(capsys):
    with pytest.raises(SystemExit) as e:
        run(["task-status", "nope"], capsys)
    assert e.value.code == 1  # 404 -> error exit


def test_simple_endpoints(capsys):
    for name in ("analytics", "providers", "security"):
        code, out = run([name], capsys)
        assert code == 0 and out.strip().startswith("{")
