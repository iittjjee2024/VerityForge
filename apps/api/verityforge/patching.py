"""Patch-based editing: validated, workspace-bound, approval-gated, concurrency-safe."""
from __future__ import annotations

import difflib
from dataclasses import dataclass

from .repo import sha_of
from .security import Action, ApprovalGate, PolicyViolation, SecurityContext, resolve_in_workspace


@dataclass
class Patch:
    path: str
    base_sha: str  # sha of the file when the agent read it
    old: str
    new: str


def read_for_edit(ctx: SecurityContext, path: str) -> tuple[str, str]:
    p = resolve_in_workspace(ctx, path)
    data = p.read_bytes()
    return data.decode("utf-8"), sha_of(data)


def _adapt(text: str, s: str) -> str:
    """Models emit LF; match the file's existing line-ending style (CRLF on Windows)."""
    return s.replace("\r\n", "\n").replace("\n", "\r\n") if "\r\n" in text else s


def validate(ctx: SecurityContext, patch: Patch) -> str:
    p = resolve_in_workspace(ctx, patch.path)
    data = p.read_bytes()
    if sha_of(data) != patch.base_sha:
        raise PolicyViolation(f"Concurrent modification detected in {patch.path}; re-read required")
    text = data.decode("utf-8")
    old = _adapt(text, patch.old)
    if text.count(old) != 1:
        raise PolicyViolation(f"Patch anchor must match exactly once in {patch.path} (found {text.count(old)})")
    return text


def _replaced(text: str, patch: Patch) -> str:
    return text.replace(_adapt(text, patch.old), _adapt(text, patch.new), 1)


def render_diff(ctx: SecurityContext, patch: Patch) -> str:
    text = validate(ctx, patch)
    new_text = _replaced(text, patch)
    return "".join(difflib.unified_diff(text.splitlines(True), new_text.splitlines(True),
                                         f"a/{patch.path}", f"b/{patch.path}"))


def apply_patch(ctx: SecurityContext, gate: ApprovalGate, patch: Patch, approval_id: str | None) -> str:
    diff = render_diff(ctx, patch)  # validates workspace, sha, anchor
    gate.enforce(approval_id, Action.WRITE_FILE, patch.path, diff)
    p = resolve_in_workspace(ctx, patch.path)
    text = p.read_bytes().decode("utf-8")
    p.write_bytes(_replaced(text, patch).encode("utf-8"))  # bytes: preserve line endings exactly
    return diff
