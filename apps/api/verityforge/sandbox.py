"""Docker sandbox. Generated commands never run on the host."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .security import Action, ApprovalGate, SecurityContext

# The single approval key for running a command in the sandbox. The agent requests approval with this target and
# run_in_sandbox enforces the same one. The image is host config (not model-controlled), so it is not part of the key.
SANDBOX_TARGET = "sandbox"


@dataclass
class SandboxLimits:
    memory: str = "512m"
    cpus: str = "1.0"
    pids: int = 128
    timeout_s: int = 120
    network: str = "none"


def build_docker_command(ctx: SecurityContext, image: str, command: list[str],
                         limits: SandboxLimits | None = None, env: dict[str, str] | None = None) -> list[str]:
    l = limits or SandboxLimits()
    args = ["docker", "run", "--rm", "--network", l.network, "--memory", l.memory, "--cpus", l.cpus,
            "--pids-limit", str(l.pids), "--read-only", "--tmpfs", "/tmp", "--user", "65534:65534",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "-v", f"{ctx.workspace_root}:/workspace:rw", "-w", "/workspace"]
    for k, v in (env or {}).items():  # explicit allow-list only; host env is never inherited
        args += ["-e", f"{k}={v}"]
    return args + [image] + command


def run_in_sandbox(ctx: SecurityContext, gate: ApprovalGate, approval_id: str | None, image: str,
                   command: list[str], limits: SandboxLimits | None = None) -> dict:
    gate.enforce(approval_id, Action.RUN_COMMAND, SANDBOX_TARGET, " ".join(command))
    l = limits or SandboxLimits()
    try:
        r = subprocess.run(build_docker_command(ctx, image, command, l), capture_output=True, text=True,
                           timeout=l.timeout_s)
        return {"executed": True, "exit_code": r.returncode, "stdout": r.stdout[-8000:], "stderr": r.stderr[-8000:]}
    except subprocess.TimeoutExpired:
        return {"executed": True, "exit_code": None, "timed_out": True}
    except OSError as e:
        return {"executed": False, "error": f"Docker unavailable: {e}"}  # reported as NOT executed
