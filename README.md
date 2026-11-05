# VerityForge

Token-efficient coding agent plus stale-answer detector, sharing one gateway, budget, cache and security layer.

## Status (honest)

Implemented and unit-tested (22 tests, mock providers only):
- Security: confidential-scope egress block, approval gate bound to exact operation, workspace path confinement, secret redaction, injection scanner.
- Gateway: provider-independent `ModelGateway`, Bifrost (OpenAI-compatible HTTP) adapter, local adapter, tier routing, health registry, bounded jittered backoff, security-aware failover (confidential fails closed), pre-call budget enforcement.
- Verification: claim extraction, freshness policy, Tavily adapter, evidence comparison, configurable scoring, conflict reporting.
- Agent tooling: git-aware indexer, symbols, import graph, incremental invalidation, budgeted context builder, patch engine with concurrency detection, Docker sandbox command builder, scoped cache.
- REST API (`/api/v1/health|verify|context|usage`), SQL migration, Compose file.

Also implemented: the agent loop (`agent.py`, approval-gated, test-verified, bounded repair), task/approval REST API (`tasks.py`), a token-efficiency benchmark (`benchmarks/token-efficiency/run.py`, scripted-model, see its header for limits), and a Next.js dashboard in `apps/web` with Dashboard, Coding Workspace and Answer Verification pages (typechecked, production build passes, pages and API proxy smoke-tested; no browser/Playwright tests yet).

Verification benchmark (`python benchmarks/verification/run.py`): 15 SYNTHETIC cases authored by the developer with mocked research. Latest run: extraction P/R 1.0/1.0 (too small and self-authored to be meaningful), status accuracy 0.933, stale-claim precision 1.0 / recall 0.833, FP rate 0.0, evidence coverage 0.917. Known failing case: leadership changes (comparison is value-based for versions, prices and percentages; entity comparison needs the LLM). These numbers do not measure live Tavily retrieval or real-world accuracy.

Getting a Bifrost key: Bifrost issues no keys. Run it yourself (`npx -y @maximhq/bifrost` or `docker run -p 8080:8080 maximhq/bifrost`), open http://localhost:8080, add an upstream provider key (OpenAI, Anthropic, Groq...), then set `BIFROST_BASE_URL=http://localhost:8080` and `VERITYFORGE_MOCK_MODE=false`. `BIFROST_API_KEY` is only needed if you enable Bifrost virtual keys. Verified on this machine: the adapter reaches a real local Bifrost, the request format is accepted, and a missing provider key is surfaced as a non-retryable error. VERIFIED LIVE (Nov 2026, Groq free tier via a local Bifrost started with `scripts/start-bifrost.ps1`, which uses `bifrost/config.json` and reads `GROQ_API_KEY` from `.env`): real completions, provider-reported token usage parsing, small/large tier routing (`groq/openai/gpt-oss-20b` / `groq/openai/gpt-oss-120b`; the Llama models were no longer available on the account), query expansion, the LLM evidence judge (against SYNTHETIC evidence), and an end-to-end agent task completed with passing tests. NOT verified live: Tavily, Docker sandbox execution (daemon not running), cross-provider failover, local-model path. Notes: gpt-oss models spend hidden reasoning tokens, so `max_output_tokens` must be generous (the adapter now raises an explicit error on an empty, truncated reply). Run the gateway on 127.0.0.1 only and keep it updated; a third-party article reports a critical Bifrost vulnerability in an older version (unverified by me).

Live token-efficiency benchmark (`python benchmarks/token-efficiency/run.py 1 3 6 --live`, 3 runs per cell, tiny synthetic repos of 3/5/8 files, provider-reported input tokens): median input tokens baseline vs optimized 995 vs 232 (3 files, -76.7%; baseline completed 2/3, optimized 3/3), 2567 vs 232 (5 files, -91.0%; both 3/3), 4925 vs 232 (8 files; baseline 1/3 because the other two runs were rejected by Groq with HTTP 413 "request too large", optimized 2/3 with one "invalid model output" failure; the baseline median comes from a single run). On repos of ~12 files and more the whole-repo baseline was rejected in every run. Small samples and tiny repos: indicative only, not a general claim.

RAG / retrieval (`retrieval.py`, `repo.py`, `expansion.py`): chunk-level BM25 retrieval over code (symbol-level chunks, cached per file hash), Reciprocal Rank Fusion, optional pluggable embedder (hashed n-gram local; `BifrostEmbedder` for neural embeddings, untested live and refused for confidential repos), LLM query expansion (sanitized, local-only for confidential, not yet wired into the agent loop), and passage-level retrieval for the evidence judge. Benchmark (`python benchmarks/retrieval/run.py`, 14 synthetic queries, easy): recall@3 0.143 (old keyword ranking) -> 1.0 (BM25); the n-gram vector hybrid did not improve it (MRR 0.929 vs 0.964), so dense retrieval is off by default.

LLM evidence judge (`judge.py`): when deterministic comparison finds no comparable value, the claim and retrieved snippets go to a small model through the gateway. The cited URL must be one of the retrieved sources and the quote must appear verbatim in that source, otherwise the verdict is discarded. Active only when a live (non-mock) model is configured. Unit-tested with scripted replies only; it has NOT been run against a real model, and the verification benchmark does not exercise it.

NOT done yet: CLI, persistence wiring to Postgres/Redis (task state is in memory), auth, Celery, plugin SDK, verification benchmark, Playwright tests, and the remaining dashboard pages (Repository, Providers, Analytics, Security, Evaluation, Settings). Dashboard metrics without a data source say "No data".

Known audit note: `npm audit` reports PostCSS advisories bundled inside Next (fix requires Next 16, a major upgrade, not yet done). They concern attacker-controlled CSS at build time; this app only builds its own CSS.

Web: `cd apps/web; npm install; npm run build; npm start` (proxies `/api/*` to `VERITYFORGE_API_URL`, default http://localhost:8000). No live Bifrost or Tavily call has been made; those adapters are untested against the real services.

## Run

```
python -m venv .venv; .\.venv\Scripts\pip install -e .[dev]
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\uvicorn verityforge.main:app --app-dir apps/api
```
Copy `.env.example` to `.env`. With no keys set, responses are labeled mock.
Targets Python 3.11+ (3.12 in Docker); local machine has 3.11.
