import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_agent import GOOD, SRC, TEST, host_pytest_runner  # fixtures; test-only host runner
from verityforge.budget import BudgetManager
from verityforge.gateway import MockProvider, ModelGateway, ModelSpec
from verityforge.tasks import TaskManager, make_router


def build(tmp_path, reply=GOOD):
    (tmp_path / "products.py").write_text(SRC)
    (tmp_path / "test_products.py").write_text(TEST)
    prov = MockProvider(responder=lambda m, r: json.dumps(reply))
    gw = ModelGateway([ModelSpec("mock-small", prov, "small")], BudgetManager(), sleep=lambda s: None)
    mgr = TaskManager(gw, lambda ctx: host_pytest_runner(str(tmp_path)), approval_timeout_s=10)
    app = FastAPI()
    app.include_router(make_router(mgr))
    return TestClient(app), mgr


def wait(fn, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("timed out")


def approve_next(c, tid):
    a = wait(lambda: c.get("/api/v1/approvals", params={"task_id": tid}).json())[0]
    assert c.post(f"/api/v1/approvals/{a['id']}/decision", json={"approve": True}).status_code == 200
    return a


def test_full_flow_pending_approvals_then_completed(tmp_path):
    c, _ = build(tmp_path)
    t = c.post("/api/v1/tasks", json={"objective": "add limit to list_products", "workspace_root": str(tmp_path)}).json()
    a1 = approve_next(c, t["id"])
    assert a1["action"] == "write_file" and "+    return items[:limit]" in a1["detail"]
    a2 = approve_next(c, t["id"])
    assert a2["action"] == "run_command"
    done = wait(lambda: (x := c.get(f"/api/v1/tasks/{t['id']}").json())["state"] == "completed" and x)
    assert done["test_runs"][-1]["result"] == "passed" and done["usage"]["model_calls"] == 1


def test_nothing_written_while_approval_pending(tmp_path):
    c, _ = build(tmp_path)
    t = c.post("/api/v1/tasks", json={"objective": "add limit to list_products", "workspace_root": str(tmp_path)}).json()
    wait(lambda: c.get("/api/v1/approvals").json())
    assert (tmp_path / "products.py").read_text() == SRC
    assert c.get(f"/api/v1/tasks/{t['id']}").json()["state"] == "awaiting_approval"


def test_cancel_releases_pending_approval(tmp_path):
    c, _ = build(tmp_path)
    t = c.post("/api/v1/tasks", json={"objective": "add limit to list_products", "workspace_root": str(tmp_path)}).json()
    wait(lambda: c.get("/api/v1/approvals").json())
    c.post(f"/api/v1/tasks/{t['id']}/cancel")
    wait(lambda: c.get(f"/api/v1/tasks/{t['id']}").json()["state"] == "cancelled")
    assert (tmp_path / "products.py").read_text() == SRC


def test_reject_via_api(tmp_path):
    c, _ = build(tmp_path)
    t = c.post("/api/v1/tasks", json={"objective": "add limit to list_products", "workspace_root": str(tmp_path)}).json()
    a = wait(lambda: c.get("/api/v1/approvals").json())[0]
    c.post(f"/api/v1/approvals/{a['id']}/decision", json={"approve": False})
    wait(lambda: c.get(f"/api/v1/tasks/{t['id']}").json()["state"] == "cancelled")
    assert (tmp_path / "products.py").read_text() == SRC


def test_confidential_task_blocked_without_local_model(tmp_path):
    c, _ = build(tmp_path)
    t = c.post("/api/v1/tasks", json={"objective": "add limit", "workspace_root": str(tmp_path),
                                      "confidential": True}).json()
    done = wait(lambda: (x := c.get(f"/api/v1/tasks/{t['id']}").json())["state"] == "failed" and x)
    assert "paused_provider" in done["outcome"] and done["usage"]["model_calls"] == 0


def test_double_decision_and_unknown_ids(tmp_path):
    c, _ = build(tmp_path)
    c.post("/api/v1/tasks", json={"objective": "add limit to list_products", "workspace_root": str(tmp_path)})
    a = approve_next(c, c.get("/api/v1/tasks").json()[0]["id"])
    assert c.post(f"/api/v1/approvals/{a['id']}/decision", json={"approve": True}).status_code == 404
    assert c.get("/api/v1/tasks/nope").status_code == 404
