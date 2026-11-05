# API reference (v1)

Base: `/api/v1`. All routes are versioned. Interactive docs at `/docs` (FastAPI/OpenAPI) when the server runs.

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | Status, research provider, model health |
| POST | `/verify` | Analyse an AI answer claim-by-claim (live Tavily + judge when configured) |
| POST | `/context` | Build a token-budgeted repo context; reports token savings vs whole-repo |
| POST | `/tasks` | Start a coding task (runs in background; returns 202) |
| GET  | `/tasks` · `/tasks/{id}` | List / inspect tasks (state, plan, diffs, tests, token usage) |
| POST | `/tasks/{id}/cancel` | Cancel a task; releases any pending approval as rejected |
| GET  | `/approvals` | Pending approvals (exact diff/command, impact, reason) |
| POST | `/approvals/{id}/decision` | `{"approve": true\|false}` — enforced by the execution layer |
| GET  | `/usage` | Per-request gateway log + estimated daily spend |
| GET  | `/analytics` | Token & cost totals, per-model, per-task, budget |
| GET  | `/providers` | Configured models: tier, scope, health, pricing |
| GET  | `/security` | Policy, sandbox limits, pending approvals, audit trail |
| GET  | `/evaluation` | Saved benchmark results (held-out live eval, dev progression, token-efficiency, offline) |

## Error contract

- `402 budget_exceeded` — a limit would be crossed; no model call is made.
- `403 policy_violation` — workspace/scope/approval policy blocked the operation.
- `404` — unknown task or already-decided approval.

## Example: verify a claim

```bash
curl -s localhost:8000/api/v1/verify -H 'content-type: application/json' \
  -d '{"answer":"Node.js 18 is the current LTS release of Node.js."}' | jq '.claims[0].status'
```

## Notes

- Costs are estimates from configured pricing, never provider billing.
- Token counts are provider-reported where available, else character-based approximations (labelled).
- No authentication yet; intended for local/trusted use. Virtual-key auth via Bifrost is supported but off.
