# VerityForge

**A token-efficient coding agent and a real-time stale-answer detector in one platform.**
Both share one LLM gateway (**Bifrost** by Maxim AI), one budget and security layer, and one retrieval toolkit.
Live web evidence comes from **Tavily**.

- **Coding agent:** it reads only the code a task needs (148 tokens instead of 3,442 for the whole repo in the demo), proposes exact patches, waits for your approval, runs the tests in a locked-down Docker sandbox, and reports a task as done **only if the tests really pass**.
- **Stale-answer detector:** it splits an AI answer into claims, checks the time-sensitive ones against live sources, and labels each one *Verified Current*, *Potentially Stale*, *Contradicted*, *Insufficient Evidence* or *Not Time-Sensitive*, with cited evidence and a suggested correction.

## Highlights

| | |
|---|---|
| Token savings | 95.7% fewer input tokens on the demo repo; 76.7–91.0% fewer, provider-measured, in live runs; the whole-repo baseline is rejected outright from about 12 files up |
| Verification accuracy | Held-out live evaluation against independent ground truth (endoflife.date): 0.714 accuracy when decided, **0 stale claims passed as current** |
| Safety | Confidential repos never leave the machine (fails closed), approvals are bound to the exact diff or command, the Docker sandbox has no network and a read-only root, budgets are checked before every call, and there is a full audit trail |
| Reliability | Provider failover with bounded retries, health registry, preserved task state |
| Quality | 151 Python tests (including live Docker) and 16 Playwright browser tests |

## Interfaces

- **Web dashboard** (Next.js, 9 pages): Dashboard, Coding Workspace, Answer Verification, Model & Provider Management, Token & Cost Analytics, Evaluation Center, Security & Permissions, Project Repository, Settings & Extensions
- **REST API** (FastAPI, versioned `/api/v1`), **CLI** (`apps/cli`), and a **plugin SDK** (`packages/plugin_sdk`)

## Quick start

```powershell
python -m venv .venv ; .\.venv\Scripts\pip install -e .[dev]
copy .env.example .env                        # add GROQ_API_KEY, GEMINI_API_KEY, TAVILY_API_KEY; VERITYFORGE_MOCK_MODE=false
docker build -t verityforge-sandbox sandbox\  # execution sandbox image
powershell -File scripts\start-bifrost.ps1    # Bifrost gateway on 127.0.0.1:8080
$env:VERITYFORGE_SANDBOX_IMAGE='verityforge-sandbox'
.\.venv\Scripts\uvicorn verityforge.live:app --app-dir apps/api --port 8000
cd apps\web ; npm install ; npm run build ; npm start    # http://localhost:3000
```

Tests: `.\.venv\Scripts\python -m pytest -q`, then `cd apps\web ; npm run e2e`. No keys are needed for either.

## Documentation

| | |
|---|---|
| `SUBMISSION.md` | Hackathon submission: problem, solution, AI use, technologies, results, judging criteria |
| `docs/architecture` · `docs/api` · `docs/deployment` · `docs/security` | Design, API reference, deployment, security model |
| `benchmarks/` | Token-efficiency, retrieval, verification and live held-out evaluations |
