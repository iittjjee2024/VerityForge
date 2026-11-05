# Security model

Security is a backend property, enforced in code (`security.py`, `gateway.py`, `patching.py`, `sandbox.py`).
Prompts, repository files, web pages, and model output are **untrusted data** and cannot change policy.

## Confidential repositories
- Marked confidential → no remote model, no remote embedder, no Tavily, no shared cache, no logs/telemetry of content.
- Enforced by `check_remote_allowed()` and `ModelGateway.select()` (remote models filtered out for confidential scope).
- **Fail-closed:** if no local model is configured, the task pauses instead of leaking. Verified by test
  `test_confidential_task_without_local_model_fails_closed`.
- A prompt/injection that says "upload the repo" is logged and ignored; it cannot flip the scope.

## Action approval
- Read-only actions run without approval. Write/exec/git/install/env/config/network require explicit approval.
- Each approval is bound to the **exact** operation (action + target + diff/command). An approval for one op cannot
  authorise another. Enforced in `ApprovalGate.enforce()`; tested by the patching and task-API suites.
- Cancel and timeout count as rejection.

## Sandboxed execution
- Generated commands run only in Docker: `--network none`, read-only root, `--cap-drop ALL`, non-root user,
  memory/CPU/PID/timeout limits. Host env is never inherited. Built by `build_docker_command()`.

## Prompt-injection defence
- `scan_untrusted()` flags injection indicators; untrusted text is wrapped and passed as data, never instructions.
- Structured tool permissions and policy checks live outside the LLM.

## Secrets & audit
- `redact_secrets()` scrubs keys/tokens from logs, errors, and the audit trail.
- `AuditLog` records approvals, blocks, confidential-egress blocks, and injection detections (secret-redacted).

## Budgets
- Per-request/task/day/month limits checked **before** each model call; unknown models priced conservatively,
  never free. A confidential task never fails over to a remote model to satisfy a budget.

## Authentication
- Signed stateless bearer tokens (HMAC-SHA256, stdlib). `POST /auth/login` issues a token; write/state-changing
  routes require it via the `require_user` dependency. Read-only GETs stay open.
- Enforced in the backend, not the UI. Tokens are tamper-evident (constant-time signature compare) and expire.
- Disabled by default for local dev (requests run as `local`); becomes required the moment `VERITYFORGE_AUTH_SECRET`
  or `VERITYFORGE_USERS` is set — configuring it never silently weakens the deployment.
- The authenticated user flows into the task security context and the audit trail (login success/failure,
  approval decisions are attributed). Demo-grade user store (`VERITYFORGE_USERS`); swap for a real IdP in production.

## Known gaps
- Demo-grade credential store (env var); no password hashing/rotation/IdP yet.
- Task state is in-memory; telemetry + audit can persist to SQLite/PostgreSQL (`VERITYFORGE_PERSIST`).
- Docker sandbox is verified live against a real daemon (`tests/integration/test_sandbox_docker.py`): non-root uid
  65534, read-only root filesystem, blocked network, writable /tmp, and approval-gating all confirmed. The test
  auto-skips when no Docker daemon is reachable, so CI without Docker stays green.
