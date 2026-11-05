"""Live Docker sandbox integration test. Skipped automatically when no Docker daemon is reachable
(so the default suite stays green in CI without Docker). Run with Docker up to exercise it.

Verifies the real security properties, not just command construction:
  non-root user, read-only root fs, no network, writable /tmp, and approval-gating.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from verityforge.sandbox import run_in_sandbox
from verityforge.security import Action, ApprovalGate, PolicyViolation, Scope, SecurityContext

IMAGE = "python:3.12-slim"


def _docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _docker_ready(), reason="Docker daemon not available")


@pytest.fixture(scope="module", autouse=True)
def _ensure_image():
    # Pull once; if the image is already present this is instant.
    subprocess.run(["docker", "pull", IMAGE], capture_output=True, timeout=300)


@pytest.fixture
def ctx():
    return SecurityContext("tester", "repo", Scope.STANDARD, tempfile.mkdtemp())


def _approved_run(ctx, command):
    gate = ApprovalGate()
    req = gate.request(Action.RUN_COMMAND, IMAGE, " ".join(command), "i", "r")
    gate.decide(req.id, True)
    return run_in_sandbox(ctx, gate, req.id, IMAGE, command)


def test_runs_non_root(ctx):
    r = _approved_run(ctx, ["python", "-c", "import os; print(os.getuid())"])
    assert r["executed"] and r["exit_code"] == 0 and r["stdout"].strip() == "65534"


def test_root_filesystem_is_read_only(ctx):
    r = _approved_run(ctx, ["python", "-c", "open('/probe','w')"])
    assert r["exit_code"] != 0 and "Read-only file system" in r["stderr"]


def test_network_is_blocked(ctx):
    r = _approved_run(ctx, ["python", "-c",
                            "import socket; socket.create_connection(('1.1.1.1', 53), 2)"])
    assert r["exit_code"] != 0  # no route / name resolution: connection cannot be made


def test_tmp_is_writable(ctx):
    r = _approved_run(ctx, ["python", "-c", "open('/tmp/ok','w').write('y'); print('ok')"])
    assert r["exit_code"] == 0 and r["stdout"].strip() == "ok"


def test_unapproved_command_never_reaches_docker(ctx):
    with pytest.raises(PolicyViolation):
        run_in_sandbox(ctx, ApprovalGate(), None, IMAGE, ["echo", "x"])
