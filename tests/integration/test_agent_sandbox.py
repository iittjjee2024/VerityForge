"""The real CodingAgent wired to the REAL sandbox runner and a real container; only the model is scripted.

This is the integration the unit tests missed: the agent's approval request and the sandbox's enforcement must use
the same key, and a model-returned test_command may be a string. Needs Docker + the `verityforge-sandbox` image
(`docker build -t verityforge-sandbox sandbox/`); skipped otherwise.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from verityforge.agent import AgentTask, CodingAgent, State, normalize_command
from verityforge.budget import BudgetManager
from verityforge.gateway import MockProvider, ModelGateway, ModelSpec
from verityforge.sandbox import run_in_sandbox
from verityforge.security import ApprovalGate, Scope, SecurityContext

IMAGE = "verityforge-sandbox"


def _ready() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


needs_docker = pytest.mark.skipif(not _ready(), reason="Docker or the verityforge-sandbox image unavailable")


def test_normalize_command_handles_string_list_and_junk():
    assert normalize_command("pytest -q") == ["pytest", "-q"]
    assert normalize_command(["pytest", "-q"]) == ["pytest", "-q"]
    assert normalize_command(None) == [] and normalize_command(5) == [] and normalize_command([1, 2]) == []
    assert normalize_command("unterminated 'quote") == []   # never raises


REPLY = {
    "criteria": ["list_products accepts limit"], "plan": ["add limit"],
    "test_command": "pytest -q",   # a STRING, as real models often return
    "edits": [{"path": "shop.py", "old": "def list_products(items):\n    return items",
               "new": "def list_products(items, limit=None):\n    return items[:limit]"}],
}


@needs_docker
def test_agent_runs_tests_in_real_sandbox_end_to_end():
    root = Path(tempfile.mkdtemp())
    (root / "shop.py").write_text("def list_products(items):\n    return items\n")
    (root / "test_shop.py").write_text(
        "from shop import list_products\n\ndef test_limit():\n    assert list_products([1, 2, 3], limit=2) == [1, 2]\n")
    (root / "pytest.ini").write_text("[pytest]\npythonpath = .\naddopts = -p no:cacheprovider\n")
    ctx = SecurityContext("tester", "repo", Scope.STANDARD, str(root))
    prov = MockProvider(responder=lambda m, r: json.dumps(REPLY))
    gw = ModelGateway([ModelSpec("mock-small", prov, "small")], BudgetManager(), sleep=lambda s: None)
    gate = ApprovalGate()
    runner = lambda cmd, aid: run_in_sandbox(ctx, gate, aid, IMAGE, cmd)  # noqa: E731 — same shape as main.py
    task = CodingAgent(gw, gate, runner, lambda req: True).run(AgentTask("add limit", ctx))
    assert task.state == State.COMPLETED, task.outcome
    assert task.outcome == "verified: tests passed"
    assert task.test_runs[-1]["result"] == "passed" and task.test_runs[-1]["command"] == ["pytest", "-q"]
    assert "limit=None" in (root / "shop.py").read_text()
