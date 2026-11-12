# VerityForge — Hackathon Submission

**Repository:** https://github.com/iittjjee2024/VerityForge
**Demo video:** _add link after recording_

One platform that solves both hackathon problem statements:
1. **A coding agent that gets the job done on the fewest tokens.**
2. **A stale-answer detector for AI applications.**

Both run on one shared foundation: the **Bifrost** LLM gateway, live **Tavily** research, backend-enforced budgets and
security, and a retrieval toolkit.

---

## 1. The problem

- **Coding agents waste tokens.** They send whole files or whole repositories to the model and repeat scans. They also
  declare success because the model says so. That is slow and expensive, and on rate-limited tiers it fails outright.
- **AI answers go stale.** Models confidently state an API version, a price, a support date or who runs a company,
  and the fact has changed. Nothing tells the user which sentence to distrust, or why.

## 2. The solution

**Coding agent.** Given a task and a repository, it:
1. builds a minimal, task-specific context (BM25 retrieval over symbol-level code chunks, plus import-graph neighbours, under a token budget);
2. plans and proposes exact patches in one model call, including creating new files such as tests;
3. shows every diff and waits for approval;
4. runs the tests in a network-less Docker sandbox, then repairs failures within a fixed limit, escalating to a larger model;
5. marks the task **complete only when the tests pass and every requested part was done**.

**Stale-answer detector.** It:
1. extracts individual factual claims and skips opinions;
2. classifies how fast each kind of fact changes (pricing, versions and support dates change fast; history is stable);
3. searches Tavily for the time-sensitive claims only;
4. compares the evidence with the claim;
5. returns a status, a transparent score, the cited sources with their dates, and a suggested correction.

Conflicting sources are shown side by side. Missing evidence is reported as unverified, never as false.

## 3. How AI is used

| Where | Technique | Guardrail |
|---|---|---|
| Coding agent | LLM plans and writes patches as structured JSON | Patches are validated, approved and test-verified; a completeness check rejects partial work |
| Token reduction | Retrieval-augmented context: BM25 code chunks, Reciprocal Rank Fusion, import-graph expansion, per-file chunk cache | Hard token budget per call |
| Model routing | Small model by default, escalation to a larger model on repair; Groq for coding, Gemini for judging, all through Bifrost | Budget checked before every call |
| Query expansion | LLM suggests likely identifiers | Output sanitised to identifier tokens only |
| Evidence judge | LLM compares a claim with retrieved passages | The cited URL must be one that was retrieved, and the quote must appear verbatim in it |
| Two-step lifecycle check | LLM only **extracts** an end-of-life date | The supported / not-supported decision is made **in code** against today's date |
| Passage retrieval | Selects the relevant window of long pages, keyed on the claim's version number | — |

## 4. Technologies and tools

| Layer | Technology |
|---|---|
| LLM gateway | **Bifrost by Maxim AI**: routing, provider failover, multi-provider (Groq + Gemini) |
| Web research | **Tavily** Search API: live evidence, publication dates, credit tracking |
| Models | Groq `gpt-oss-20b` / `gpt-oss-120b`, Gemini `flash-lite` |
| Backend | Python 3.12, FastAPI |
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS |
| Data | PostgreSQL + pgvector schema; SQLite / PostgreSQL persistence for telemetry and audit |
| Execution | Docker sandbox: no network, read-only root, non-root, all capabilities dropped, resource limits |
| Auth | HMAC-signed bearer tokens, PBKDF2-HMAC-SHA256 password hashing |
| Testing | pytest (151), Playwright (16) |
| Deployment | Docker Compose |

## 5. Features delivered

- **Web dashboard, 9 pages:** Dashboard, Coding Workspace, Answer Verification, Model & Provider Management, Token &
  Cost Analytics, Evaluation Center, Security & Permissions, Project Repository, Settings & Extensions.
- **REST API** (versioned `/api/v1`), **CLI**, and a **plugin SDK** with host-enforced permissions.
- **Security:**
  - Confidential repos stay local and fail closed.
  - Approvals are bound to the exact operation.
  - Commands run in the Docker sandbox.
  - Prompt-injection scanning, secret redaction, and an audit trail.
- **Cost control:** per-request, per-task, daily and monthly budgets, enforced in the backend before every model call.
- **Reliability:** bounded exponential backoff with jitter, a provider health registry, and security-aware failover.
- **Persistence:** telemetry and audit survive restarts on SQLite or PostgreSQL.

## 6. Results (measured, live services)

| Measure | Result |
|---|---|
| Context for the demo coding task | **148 tokens vs 3,442** for the whole repo (95.7% fewer) |
| Live token benchmark (provider-reported) | 76.7% fewer at 3 files, 91.0% fewer at 5 files; the whole-repo baseline is rejected as "too large" from about 12 files, while the optimized agent keeps working |
| Scripted token benchmark | 96.8–99.8% fewer input tokens, with both baseline and optimized runs completing |
| Live held-out verification (independent gold: endoflife.date) | Accuracy when decided **0.714**; **0 stale claims passed as current**; false-alarm rate halved vs the no-LLM baseline (0.333 vs 0.667) |
| Offline verification benchmark | Status accuracy 0.933, false-positive rate 0.0 |
| Code retrieval | Recall@3 rose from 0.143 to 1.0 with BM25 chunk retrieval |
| Full coding task (pagination: backend, frontend and tests) | Completed and test-verified in live runs; runs that fell short were reported as failures, never as false success |
| Outage, confidential and budget scenarios | All pass live: fallback with no wasted retries; 0 remote calls for a confidential repo; stopped before an unaffordable call |
| Automated tests | **151 pytest + 16 Playwright**, all passing |

Evaluation data and saved results: `benchmarks/`.

## 7. Judging criteria

- **Innovation:**
  - The two-step lifecycle check takes date reasoning away from the small model and does it in code, which raised held-out accuracy when decided from about 0.5 to 0.71.
  - Citations are verified, so a judge verdict with a fabricated source is discarded.
  - Failover respects security scope, so a confidential task can never fail over to a remote model.
- **Technical execution:**
  - 167 automated tests.
  - Live Bifrost, Groq, Gemini, Tavily and Docker.
  - Held-out evaluation against independent ground truth.
  - Every defect found in live runs was fixed with a regression test.
- **Problem and impact:** Fewer tokens to ship working code, and evidence-backed freshness checks on AI answers, in one platform.
- **Use of AI:** Agent planning and patching, an evidence judge, model routing, RAG and query expansion. Each has a deterministic guardrail.
- **User experience:**
  - Developer-workstation dashboard.
  - Live approvals that show the exact diff.
  - Evidence with sources, dates and conflicts.
  - Estimated and mock values are always labelled.
- **Scalability and potential:**
  - Modular monolith with provider abstraction.
  - Versioned API and plugin contract.
  - Persistence and Docker Compose deployment.

## 8. Submission checklist

| Requirement | Delivered |
|---|---|
| Working project / demo | Full stack runs locally (see `README.md` quick start); five scenarios run live against real services |
| Source code / repository | https://github.com/iittjjee2024/VerityForge |
| Project description | This document and `README.md` |
| Problem being solved | Section 1 |
| Technologies and tools used | Section 4 |
| How AI is used | Section 3 |
| Demo video | _add link after recording_ |
| Build resource: Bifrost | Used as the LLM gateway for every model call |
| Slides | Provided separately with the submission |

## 9. Responsible development

VerityForge never claims success without passing tests. It never calls a claim false for lack of evidence, and never
sends confidential code to a remote service. It labels estimated and mock values as such. It contains no malicious
functionality. API keys live only in a gitignored `.env`.

## 10. Roadmap

Enterprise identity provider (SSO), Redis as a shared cache tier, a local-model deployment profile for confidential
teams, and the Next.js 16 upgrade.
