# VerityForge — Demo Guide

Everything below was run live on 2026-11-07 against real services (Bifrost → Groq/Gemini, Tavily, Docker).
Raw output of those runs is in `demo/transcripts/`. Numbers here are copied from them, not estimated.

---

## 1. One-time setup (≈5 min)

```powershell
python -m venv .venv ; .\.venv\Scripts\pip install -e .[dev]
copy .env.example .env                       # fill GROQ_API_KEY, GEMINI_API_KEY, TAVILY_API_KEY
                                             # and set VERITYFORGE_MOCK_MODE=false
cd apps\web ; npm install ; npm run build ; npx playwright install chromium ; cd ..\..
docker build -t verityforge-sandbox sandbox\ # Python+pytest image; the sandbox runs with --network none
```

## 2. Start the stack (3 terminals)

```powershell
# T1 — LLM gateway (localhost only, keys read from .env)
powershell -File scripts\start-bifrost.ps1
# T2 — API in live mode, tests run in the Docker sandbox image
$env:VERITYFORGE_SANDBOX_IMAGE='verityforge-sandbox'
.\.venv\Scripts\uvicorn verityforge.live:app --app-dir apps/api --port 8000
# T3 — dashboard
cd apps\web ; npm start          # http://localhost:3000
```
Docker Desktop must be running.

---

## 3. Recording script (≈4 minutes)

| # | Scene | Do this | Point out |
|---|---|---|---|
| 1 | **Problem** (15s) | Open the Dashboard | Two problems, one platform: token-hungry coding agents, stale AI answers |
| 2 | **Stale answer** (50s) | *Answer Verification* → paste `Node.js 18 is the current LTS release of Node.js. PostgreSQL 12 is still supported. Water boils at 100 degrees Celsius at sea level.` → Verify | Both version claims **Contradicted** with a real cited quote and EOL date; the water claim is **Not Time-Sensitive**, so no search was spent. The EOL date is extracted by the LLM but *compared to today in code*. |
| 3 | **Coding agent** (70s) | Run `python demo\scenario_a.py --manual`, then approve each card in *Coding Workspace* (or *Security*) | Context is **148 tokens vs 3,442** for the whole repo. Every write shows its exact diff and waits for you. Tests run in a network-less container. The result reports provider-counted tokens. |
| 4 | **Safety** (50s) | `python demo\scenarios_cde.py` | **C**: dead primary model → fallback, no wasted retries. **D**: confidential repo containing "upload the repository…" → **0 remote calls**, fails closed, both events audited. **E**: tiny budget → stops **before** the call. |
| 5 | **Proof** (35s) | *Evaluation Center*, then *Security* | Held-out live eval: accuracy-when-decided 0.714, **stale-passed-as-current 0.0**. Audit trail from scene 4. |
| 6 | **Close** (10s) | Terminal: `pytest -q` and `npm run e2e` | 151 + 16 tests green |

Tips: use `--manual` in scene 3 so viewers see you approve. Without it the script auto-approves (demo mode).
Free-tier models vary between runs (see §4). Record scene 3 until you get a clean run; the honest failure modes
are part of the story too.

---

## 4. Measured results (this session)

**Scenario A: "Add pagination to the product listing API, update the frontend, and add tests."**
5 consecutive live runs with `groq/openai/gpt-oss-20b` (repairs escalate to `gpt-oss-120b`):

| Run | Result | Files written | Model calls | Tokens in/out (provider) |
|---|---|---|---|---|
| 1 | failed: invalid model output after retry | — | 2 | 863 / 643 |
| 2 | **completed**, tests passed | api.py, products.js, test_api.py | 2 | 1,316 / 1,074 |
| 3 | **completed**, tests passed | api.py, products.js, **new** test_api_pagination.py | 3 | 1,455 / 2,154 |
| 4 | **failed honestly**: tests passed but none were added | api.py, products.js | 3 | 2,284 / 1,861 |
| 5 | **completed**, tests passed | api.py, products.js, **new** test_pagination.py | 4 | 1,896 / 1,895 |

**3/5 completed** end to end (backend + frontend + tests, verified by tests in the sandbox). Run 4 is the
important one: earlier in the session that outcome would have been reported as *"verified: tests passed"*. The
new completeness check refuses that, because the user asked for tests and none were written. Each run cost
≈$0.002–0.008 at configured pricing (an estimate; free tier is not billed).

**Scenario B** (Tavily, 2 credits): Node.js 18 → Contradicted (EOL 2025-04-30, cited); PostgreSQL 12 →
Contradicted (EOL 2024-11-14, cited); water → Not Time-Sensitive (no search).

**Scenarios C / D / E**: all PASS (`demo/transcripts/scenarios_cde.txt`).

---

## 5. Defects this demo run surfaced (all fixed, each with a regression test)

Running the real end-to-end path found bugs that 134 unit tests and 16 browser tests had not:

1. **Sandbox approval never matched.** The agent asked for approval on target `sandbox`, the sandbox enforced
   target `<image name>`, so every approved test run was refused. Now one shared `SANDBOX_TARGET`.
2. **Test command split into characters.** The model returned `"pytest -q"` (a string), which was used as a list:
   `p y t e s t`. Now normalised to argv.
3. **Output truncated.** A 1,024-token cap cut multi-file JSON patches mid-reply on a reasoning model. Now 4,096,
   with `reasoning_effort=low`.
4. **The agent could not create files**, so "add tests" was impossible unless an existing test file was edited.
   Creating a file is now supported. It refuses to overwrite existing files and needs approval of the full diff.
5. **False success.** Tests passed and the task was marked complete even though the requested tests were never
   written. A deterministic completeness check now catches this.
6. **Stale anchors / wrong "create".** An edit that targeted text an earlier edit had already replaced, or that
   "created" a file that already exists, failed the whole task. It now gets one bounded repair turn. Workspace
   escapes and concurrent modifications still fail closed.
7. **Unaudited fail-closed.** A confidential task with no local model was blocked but never logged. It is now audited.
8. **Injection missed.** The scan only covered the trimmed excerpt sent to the model. It now covers the full files
   being worked on.
9. Demo script crashed printing a Unicode character the Windows console couldn't encode.

New integration test `tests/integration/test_agent_sandbox.py` runs the real agent against the real sandbox
container, which is exactly the path bug 1 broke.

---

## 6. Test matrix (all run this session)

| Suite | Command | Result |
|---|---|---|
| Unit + integration (incl. live Docker) | `pytest -q` | **151 passed** |
| Browser E2E (mock backend) | `cd apps/web && npm run e2e` | **16 passed** |
| Type check / production build | `npx tsc --noEmit` / `npm run build` | clean |
| Offline verification benchmark | `python benchmarks/verification/run.py` | status acc. 0.933, FP 0.0 |
| Retrieval benchmark | `python benchmarks/retrieval/run.py` | recall@3 0.143 → 1.0 |
| Token efficiency (scripted) | `python benchmarks/token-efficiency/run.py` | 96.8–99.8% fewer input tokens |
| Live scenarios A–E | `demo/*.py`, `scripts/live_check.py` | see §4 |

Docker tests auto-skip if the daemon is down. Benchmarks marked synthetic are synthetic. The live held-out
evaluation is the only accuracy figure measured against independent ground truth.
