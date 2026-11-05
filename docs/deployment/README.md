# Deployment & setup

## Prerequisites
- Python 3.11+ (3.12 in the Docker image), Node.js 18+, and optionally Docker (for the execution sandbox).
- A Bifrost gateway (you run it; it issues no keys) + at least one provider key (Groq free tier works).
- Optional: a Tavily key for live web verification.

## Local run
```powershell
python -m venv .venv ; .\.venv\Scripts\pip install -e .[dev]
.\.venv\Scripts\python -m pytest                 # 96 tests, no keys needed
copy .env.example .env                             # fill GROQ_API_KEY, TAVILY_API_KEY, GEMINI_API_KEY
powershell -File scripts/start-bifrost.ps1         # gateway on 127.0.0.1:8080 (reads keys from .env)
.\.venv\Scripts\uvicorn verityforge.live:app --app-dir apps/api --port 8000
cd apps/web ; npm install ; npm run build ; npm start   # http://localhost:3000
```

## Environment (.env)
| Var | Meaning |
|---|---|
| `BIFROST_BASE_URL` | Gateway URL (default `http://localhost:8080`) |
| `VERITYFORGE_MOCK_MODE` | `false` to use the live gateway; `true` for deterministic mocks |
| `VERITYFORGE_SMALL_MODEL` / `_LARGE_MODEL` | Agent models (`<provider>/<model>`) |
| `VERITYFORGE_JUDGE_MODEL` | Verification judge model (default Gemini flash-lite) |
| `VERITYFORGE_FALLBACK_MODEL` | A model on a different provider, for failover |
| `VERITYFORGE_PRICING` | `{"model":[in_per_M,out_per_M]}` for budget enforcement |
| `TAVILY_API_KEY` | Live web research (else mock, clearly labelled) |

Keys live only in `.env` (gitignored). `bifrost/config.json` references them as `env.VAR`, so no secret is committed.

## Docker Compose
`docker-compose.yml` brings up PostgreSQL (pgvector), Redis, and the API. The DB migration seeds the schema.
Note: the app does not yet read/write PostgreSQL (state is in-memory); Compose is provided for the target topology.

## Benchmarks
```
python benchmarks/token-efficiency/run.py 10 50 200     # + --live for provider-reported tokens
python benchmarks/verification/run.py                   # offline synthetic
python benchmarks/retrieval/run.py                      # offline synthetic
python benchmarks/live/build_dataset.py                 # refresh gold from endoflife.date
python benchmarks/live/run.py --set dev --replay-only   # validate on recorded evidence (no credits)
python benchmarks/live/run.py --set heldout             # one-shot held-out figure
```
