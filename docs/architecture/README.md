# Architecture

VerityForge is a **modular monolith**: one FastAPI backend with clear service-boundary modules that can be
extracted into services later. One Next.js frontend. One LLM gateway (Bifrost). State is in-memory today; the
PostgreSQL schema exists (`database/migrations/0001_init.sql`) but is not yet wired in.

## Modules (apps/api/verityforge/)

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI app, dependency wiring, REST routes, error handlers |
| `security.py` | Scopes, approval gate, workspace confinement, secret redaction, injection scan, **audit log** — all enforced in code, never by prompts |
| `gateway.py` | Provider-independent `ModelGateway`; Bifrost / local / mock providers; tier routing; health registry; bounded-backoff, security-aware failover |
| `budget.py` | Per-request/task/day/month limits enforced **before** each model call; configurable pricing |
| `verification.py` | Claim extraction, freshness policy, evidence comparison, transparent scoring |
| `judge.py` | LLM evidence judge + **two-step lifecycle judge** (extract EOL date → compare in code); citation verification |
| `research.py` | Tavily adapter + mock; secret-safe |
| `retrieval.py` | BM25 chunk retrieval, RRF, pluggable embedder, passage selection |
| `repo.py` | Git-aware indexer, symbols, import graph, incremental invalidation, token-budgeted context |
| `agent.py` | Coding-agent state machine: plan → approve → patch → test → bounded repair → verify |
| `patching.py` | Validated, workspace-bound, approval-gated, concurrency-safe edits |
| `sandbox.py` | Docker command builder: no network, read-only root, dropped caps, non-root |
| `cache.py` | Scope-keyed cache; confidential results never cached |
| `tasks.py` | Background task manager; approvals block until decided over HTTP |

## Key design decisions

- **Provider independence.** Business logic depends only on `ModelGateway`. Bifrost is one provider behind it; it
  can be swapped without touching the agent or verifier.
- **Security is code, not prompts.** Confidential egress, approvals, and workspace confinement are enforced in the
  execution layer. A prompt (or injected repo text) cannot widen permissions.
- **Honesty by construction.** Mock/estimated/unverified results are labelled as such; a task is "complete" only on
  executed passing tests; an unverifiable claim is never called false.

## Request flow (coding task)

```
POST /tasks → TaskManager starts agent thread
  → RepoIndex.build_context (BM25, token budget)
  → ModelGateway.complete (budget precheck → provider → usage)
  → patch proposed → ApprovalGate.request → (pauses; HTTP approve/reject)
  → apply patch → run tests in sandbox → bounded repair → COMPLETED iff tests pass
```

## Diagram

See `docs/architecture/diagram.md` for a component diagram.
