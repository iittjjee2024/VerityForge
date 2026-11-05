# VerityForge

One platform for two problems: a **coding agent that gets the job done on the fewest tokens**, and a **stale-answer detector** for AI output. Both share one model gateway (Bifrost), one budget and security layer, and one retrieval toolkit.

## The problem

1. **Coding agents waste tokens.** Typical agents send whole files or whole repositories to the model, repeat scans, and declare success on the model's say-so. That is slow, expensive, and on free or rate-limited tiers it often fails outright.
2. **AI answers go stale.** A model confidently states an API version, a price, or who runs a company, and it is out of date. Nothing tells the user which sentences to distrust or why.

## What it does

**Coding agent.** Given a task and a repository, it builds a small, task-specific context (BM25 retrieval over symbol-level code chunks, import-graph neighbours, token budget), asks the model for a plan plus exact patches in one call, shows each diff, and applies it only after approval. It runs the tests, repairs failures within a limit (escalating to a larger model), and marks a task **complete only if the tests actually passed**. Unexecuted or unproposed tests end the task as "unverified", never as success.

**Stale-answer detector.** It extracts individual factual claims from an answer (skipping opinions), classifies how fast each kind of fact changes (pricing and API versions are "rapid", history is "stable"), searches the live web through Tavily for the time-sensitive ones, compares the evidence with the claim, and reports one of: Verified Current, Potentially Stale, Contradicted, Insufficient Evidence, Not Time-Sensitive, Verification Failed. Scores are labelled as indicators, not probabilities. Conflicting sources are shown side by side. When search is unavailable, the claim is "Verification Failed", never "false".

## How AI is used

| Where | Technique |
|---|---|
| Coding agent | LLM plans and writes patches; output is structured JSON, validated, and untrusted |
| Token reduction | Retrieval-augmented context: BM25 over code chunks, Reciprocal Rank Fusion, import-graph expansion, per-file chunk caching |
| Model routing | Small model by default, escalation to a larger model on repair; configurable tiers |
| Retrieval | Optional LLM query expansion (identifier suggestions, sanitised); pluggable neural embedder (off by default, see results) |
| Verification | Rule-based claim extraction and numeric comparison first; an LLM "judge" only when no comparable value exists. Its citation is accepted only if the URL was actually retrieved and the quoted text appears verbatim in that source |
| Evidence | Passage-level retrieval so the judge sees the relevant part of long pages |

## Technologies

Python 3.11+ and FastAPI; Next.js, React, TypeScript, Tailwind; **Bifrost** (Maxim AI) as the LLM gateway; **Tavily** for live web research; Groq models (`gpt-oss-20b`, `gpt-oss-120b`) through Bifrost; PostgreSQL + pgvector schema (migration written, not yet wired); Docker sandbox for command execution; pytest.

## Safety design

- **Confidential repositories** are enforced in backend code: no remote model, no remote embedder, no shared cache. If no local model exists, the task fails closed. Prompts cannot override it.
- **Approvals** are bound to the exact operation (a patch's diff, a command), so an approval for one thing cannot authorise another. Cancel and timeout count as rejection.
- **Untrusted data:** repository files, web pages, test output and model replies are treated as data. Injection indicators are flagged, and the model never gets to widen permissions.
- **Budgets** (per request, task, day, month) are enforced in the backend before each model call. Models with no configured price are costed conservatively, never as free.
- **Sandbox** command builder: no network, read-only root, dropped capabilities, non-root, memory/CPU/pid limits.
- Secrets are redacted from logs and error messages; keys live only in a gitignored `.env`.

## Results (what was actually measured)

**Live (Groq free tier through a local Bifrost, tiny synthetic repos, 3 runs per cell):**

| Repo files | Baseline (whole repo) median input tokens | Optimized | Savings | Completed (baseline / optimized) |
|---|---|---|---|---|
| 3 | 995 | 232 | 76.7% | 2/3 / 3/3 |
| 5 | 2,567 | 232 | 91.0% | 3/3 / 3/3 |
| 8 | 4,925 (one successful run) | 232 | not reliable | 1/3 / 2/3 |

At about 12 files and above, every baseline run was rejected by the provider as "request too large", while the optimized agent kept completing. One optimized run failed with invalid model output. Samples are small and the repos are tiny, so these numbers are indicative, not a general claim. Token counts are provider-reported.

**Retrieval (synthetic, 14 queries, easy):** recall@3 rose from 0.143 (old keyword ranking) to 1.0 (BM25 chunks). The n-gram vector hybrid did *not* help (MRR 0.929 vs 0.964), so dense retrieval is off by default.

**Verification (synthetic, 15 cases written by the developer, mocked search):** status accuracy 0.933, stale-claim precision 1.0, recall 0.833, false-positive rate 0.0. One known miss: a leadership change without the LLM judge. This measures the comparison and scoring logic, **not** live retrieval quality or real-world accuracy.

**Defects found by running against real Tavily results (all fixed, each with a regression test):** Tavily dates are RFC 2822 not ISO, so every source was scored "unknown recency"; version-index pages that list dozens of versions counted as "supporting" any claim; "Node.js" was split into two sentences; stable facts without "is/are" were dropped; the asserted value leaked into the search query; entity names were duplicated; judge quotes could be verbatim but meaningless fragments; official domains (python.org, nodejs.org) were scored as unknown reliability.

**Two-step lifecycle verification:** for "is version X still supported?" claims, the LLM only *extracts* the end-of-life date (with a verbatim, format-checked citation); the supported/not decision is made in code by comparing to today. Moving the temporal reasoning out of the small model raised held-out accuracy-when-decided from ~0.5 to 0.71 and eliminated run-to-run flakiness. Cross-provider routing (Groq for the coding agent, Gemini for the judge) runs through the single Bifrost gateway.

**Tests:** 94 automated tests pass (security policy, approvals, failover, budgets, patching, retrieval, agent loop, task API, Tavily adapter, two-step lifecycle judge, regressions from live runs).

## Honest status

| Area | Status |
|---|---|
| Bifrost gateway, completions, usage parsing, tier routing | Tested live |
| Coding agent end to end with a real model | Tested live (small tasks, host pytest) |
| LLM judge and query expansion | Tested live, on synthetic evidence |
| Tavily live search + LLM judge | Evaluated against independent ground truth (endoflife.date API) on a held-out product set never used during development. Judge model gemini-flash-lite-latest via Bifrost. Held-out: accuracy-when-decided 0.714, coverage 0.583, **stale-claim-passed-as-current 0.0**, false-alarm rate halved vs the no-LLM baseline, controls 6/6, run-to-run consistency 1.0. Small sample (12 time-sensitive claims x 3 repeats) — indicative, not a precise rate. See `benchmarks/live/FINDINGS.md`. |
| Docker sandbox execution | Command construction tested; no container run (daemon unavailable) |
| Cross-provider failover | Tested with mocks only (one live provider configured) |
| Local-model path for confidential repos | Tested with mocks only |
| Dashboard | All 9 pages (Dashboard, Coding Workspace, Answer Verification, Model & Provider Management, Token & Cost Analytics, Evaluation Center, Security & Permissions, Project Repository, Settings & Extensions); typechecks, production build passes, pages + API proxy smoke-tested live; no browser/Playwright tests. Evaluation Center reads saved benchmark files (no invented numbers). Security shows live approvals + real audit trail. Settings manages the plugin registry; Repository shows the token-minimizing context build live. |
| CLI | `apps/cli/verityforge_cli.py` — thin REST client (health, verify, context, task with --poll/--auto-approve, approvals, analytics, providers, security); 7 tests against the real app |
| Persistence | `storage.py` — SQLite or PostgreSQL; telemetry + audit survive restarts; off by default (`VERITYFORGE_PERSIST`); analytics/security endpoints read cross-restart history; 4 tests |
| Plugin SDK | `packages/plugin_sdk` + `plugins/` — manifest, declared permissions enforced by the host (plugin cannot self-grant), schema validation, enable/disable/upgrade, registry endpoints; 8 tests |
| CLI, Postgres/Redis persistence, authentication, plugin SDK, Playwright tests | Not built |

Known issue: `npm audit` reports PostCSS advisories bundled inside Next.js; the fix is a major upgrade not yet done.

## Run it

```
python -m venv .venv ; .\.venv\Scripts\pip install -e .[dev]
.\.venv\Scripts\python -m pytest                      # 96 tests, no keys needed
copy .env.example .env                                  # add GROQ_API_KEY (and TAVILY_API_KEY)
powershell -File scripts/start-bifrost.ps1              # local gateway on 127.0.0.1:8080
.\.venv\Scripts\uvicorn verityforge.live:app --app-dir apps/api --port 8000
cd apps/web ; npm install ; npm run build ; npm start  # http://localhost:3000
python scripts/live_check.py "An AI answer to verify"   # live Tavily + LLM check
python benchmarks/token-efficiency/run.py 1 3 6 --live  # live token comparison
```

## Responsible development

The tool defends against its own failure modes: it will not claim success without passing tests, will not call a claim false for lack of evidence, will not upload confidential code, and labels mock, estimated, and unverified results as such. It contains no malicious functionality.


## Submission checklist (hackathon section 7)

| Requirement | Where |
|---|---|
| Working project / demo | Live FastAPI backend + Next.js dashboard (7 pages); `scripts/live_check.py` runs the live pipeline |
| Source code / repository | This monorepo (`apps/`, `benchmarks/`, `database/`, `docs/`, `scripts/`) |
| Project description | Top of this file + `README.md` |
| Problem being solved | "The problem" section above — token-wasteful coding agents and stale AI answers |
| Technologies & tools | "Technologies" section; Bifrost + Tavily integrated and exercised live |
| How AI is used | "How AI is used" table above |
| Demo video (if required) | Not recorded; 3-minute script below |
| Build resource (Bifrost) | Used as the LLM gateway; setup in `docs/deployment` |

## Judging criteria (hackathon section 10) — self-assessment

Honest mapping; measured numbers, not aspirations.

- **Innovation.** Two-step lifecycle verification (LLM extracts the EOL date, code compares to today) removes
  temporal reasoning from a small model and raised held-out accuracy-when-decided from ~0.5 to 0.71. Security-aware
  model failover that fails closed for confidential repos. Token-minimising RAG over code.
- **Technical execution.** 96 automated tests; live Bifrost (Groq + Gemini) and live Tavily; held-out evaluation
  against independent ground truth; 7 dashboard pages; bugs found by live runs were fixed with regression tests.
- **Problem & potential impact.** Addresses both hackathon problems in one platform with shared gateway, budget,
  security and retrieval — fewer tokens to ship code, and evidence-backed freshness checks on AI answers.
- **Use of AI.** Agent planning/patching, an evidence judge with verified citations, model routing by task
  complexity, RAG retrieval, and query expansion — each with a guardrail (tests-pass, verbatim-citation, budget).
- **User experience.** Dark developer workstation UI; live approvals with the exact diff/command; evidence shown
  with sources, dates and conflicts; every estimated/mock/unverified value is labelled.
- **Scalability & potential.** Modular monolith with provider abstraction and a DB schema ready for persistence;
  clear extraction points for services; plugin/extension tables defined. Honest gaps listed below.

## Authentication
Signed bearer tokens (HMAC-SHA256, stdlib — no new dependency). `POST /auth/login` → token; write routes require it
via a backend dependency; GETs stay open. Disabled by default for local dev, required the moment
`VERITYFORGE_AUTH_SECRET`/`VERITYFORGE_USERS` are set. The authenticated user flows into the task scope and audit
trail. Tamper-evident (constant-time compare), expiring tokens. 10 tests + live end-to-end check (no-token 401,
login, authed write 202, bad-password 401, open GET 200). Web: token in localStorage, sign-in control shown only
when auth is enabled. Demo-grade user store; swap for a real IdP in production.

## Honest gaps (not claimed as done)
Password hashing / real identity provider (credentials are env-var, demo-grade); Redis (PostgreSQL persistence is
wired, Redis is not); live Docker sandbox container run. The two Python "latest version" live-eval errors trace to
version-table retrieval. Live-eval samples are small — indicative, not precise rates.
125 Python tests + 16 Playwright E2E tests pass.

## End-to-end browser tests
`cd apps/web && npm run e2e` (needs `npx playwright install chromium` once). Playwright starts the mock-mode API
(no keys, deterministic) and the Next.js server, then drives a real browser: all 9 pages render their live data,
navigation works, and the key flows (verify, context build, plugin toggle, auth-disabled state, providers in mock
mode) are asserted. 16 tests, all passing.

## Demo video

Not recorded. Suggested 3-minute script: (1) paste a stale answer into Answer Verification, show cited evidence and
the two-step lifecycle verdict; (2) run a coding task, review the diff, approve, watch tests pass and the token
report; (3) mark a repo confidential and show the backend refusing remote processing; (4) open Evaluation Center for
the held-out numbers and Security for the live audit trail.
