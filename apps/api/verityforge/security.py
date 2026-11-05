"""Security and policy engine. Enforced in backend code, never by prompts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


import threading
import time


class PolicyViolation(Exception):
    """Raised when an operation is blocked by policy."""


class AuditLog:
    """Append-only, in-memory record of security-relevant events. Thread-safe. Values are secret-redacted."""

    def __init__(self, cap: int = 500):
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self._cap = cap
        self.sink = None  # optional persistence hook (set by the API layer)

    def record(self, event: str, severity: str = "info", **detail) -> None:
        clean = {k: (redact_secrets(v) if isinstance(v, str) else v) for k, v in detail.items()}
        row = {"ts": time.time(), "event": event, "severity": severity, **clean}
        with self._lock:
            self._events.append(row)
            if len(self._events) > self._cap:
                self._events = self._events[-self._cap:]
        if self.sink:
            try:
                self.sink(row)
            except Exception:  # noqa: BLE001 — persistence must never break enforcement
                pass

    def events(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(reversed(self._events[-limit:]))


AUDIT = AuditLog()  # process-wide; a persistent store would back this in production


class Scope(str, Enum):
    STANDARD = "standard"
    CONFIDENTIAL = "confidential"


class Action(str, Enum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    RUN_COMMAND = "run_command"
    GIT_MODIFY = "git_modify"
    INSTALL_PACKAGE = "install_package"
    READ_ENV = "read_env"
    CHANGE_CONFIG = "change_config"
    NETWORK = "network"


READ_ONLY_ACTIONS = {Action.READ_FILE}


@dataclass(frozen=True)
class SecurityContext:
    """Immutable security scope carried with every task and model request."""
    user_id: str
    repo_id: str
    scope: Scope = Scope.STANDARD
    workspace_root: str = ""
    declassified_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def confidential(self) -> bool:
        return self.scope == Scope.CONFIDENTIAL

    def cache_namespace(self) -> str:
        return f"{self.user_id}:{self.repo_id}:{self.scope.value}"


def check_remote_allowed(ctx: SecurityContext, contains_repo_content: bool = True) -> None:
    """Block remote egress (gateway, Tavily) of confidential repo content."""
    if ctx.confidential and contains_repo_content:
        AUDIT.record("confidential_egress_blocked", "warning", user=ctx.user_id, repo=ctx.repo_id,
                     detail="Remote egress of confidential repository content blocked")
        raise PolicyViolation(
            "Confidential repository content may not leave local processing boundaries."
        )


def resolve_in_workspace(ctx: SecurityContext, path: str) -> Path:
    root = Path(ctx.workspace_root).resolve()
    target = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if target != root and root not in target.parents:
        raise PolicyViolation(f"Path outside authorized workspace: {path}")
    return target


def requires_approval(action: Action) -> bool:
    return action not in READ_ONLY_ACTIONS


@dataclass
class ApprovalRequest:
    id: str
    action: Action
    target: str
    detail: str  # exact command or patch
    impact: str
    reason: str
    status: str = "pending"  # pending|approved|rejected


class ApprovalGate:
    """Execution layer gate: operations run only with an approved request."""

    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._n = 0

    def request(self, action: Action, target: str, detail: str, impact: str, reason: str) -> ApprovalRequest:
        self._n += 1
        req = ApprovalRequest(f"apr-{self._n}", action, target, detail, impact, reason)
        self._requests[req.id] = req
        AUDIT.record("approval_requested", "info", action=action.value, target=target, impact=impact)
        return req

    def decide(self, request_id: str, approve: bool) -> ApprovalRequest:
        req = self._requests[request_id]
        if req.status != "pending":
            raise PolicyViolation("Approval already decided")
        req.status = "approved" if approve else "rejected"
        AUDIT.record("approval_" + req.status, "info" if approve else "warning",
                     action=req.action.value, target=req.target, reason=req.reason)
        return req

    def enforce(self, request_id: str | None, action: Action, target: str, detail: str) -> None:
        """Raise unless an approved request matches this exact operation."""
        if not requires_approval(action):
            return
        req = self._requests.get(request_id or "")
        if (
            req is None
            or req.status != "approved"
            or req.action != action
            or req.target != target
            or req.detail != detail
        ):
            AUDIT.record("operation_blocked", "error", action=action.value, target=target,
                         detail="No matching approved request; execution refused")
            raise PolicyViolation(f"Approval required for {action.value} on {target}")


_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\btvly-[A-Za-z0-9\-]{16,}\b"),
]


def redact_secrets(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore (all |any )?(previous|prior|above) (instructions|rules)"),
    re.compile(r"(?i)(upload|send|post|exfiltrate).{0,60}(repo|repository|source|code|secrets?).{0,60}(to|http)"),
    re.compile(r"(?i)disable (the )?(security|approval|policy|confidential)"),
    re.compile(r"(?i)mark (this )?(repo|repository) (as )?(public|non-?confidential)"),
    re.compile(r"(?i)you are now|new system prompt"),
]


def scan_untrusted(text: str, source: str = "untrusted") -> list[str]:
    """Return matched injection indicators. Untrusted text is data, never instructions."""
    hits = [p.pattern for p in _INJECTION_PATTERNS if p.search(text)]
    if hits:
        AUDIT.record("injection_indicator_detected", "warning", source=source, indicators=len(hits),
                     detail="Injection-like text in untrusted content; treated as data")
    return hits


def wrap_untrusted(label: str, text: str) -> str:
    return f"<untrusted source={label!r}>\n{redact_secrets(text)}\n</untrusted>"
