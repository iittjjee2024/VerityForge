"""FastAPI entrypoint (v1). Mock mode is used only when no live keys are configured."""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .budget import BudgetExceeded, BudgetManager, Pricing
from .gateway import BifrostProvider, LocalProvider, MockProvider, ModelGateway, ModelSpec
from .judge import LLMJudge
from .repo import RepoIndex
from .research import MockResearch, ResearchUnavailable, TavilyResearch
from .security import PolicyViolation, Scope, SecurityContext
from .verification import VerificationEngine

from .storage import make_store  # noqa: E402

app = FastAPI(title="VerityForge", version="0.1.0")
budget = BudgetManager()

# Persistence: set DATABASE_URL (sqlite:///file.db or postgres://...) to survive restarts; else in-memory.
store = make_store(os.getenv("VERITYFORGE_STORE_URL") or os.getenv("DATABASE_URL")
                   if os.getenv("VERITYFORGE_PERSIST", "").lower() == "true" else None)


_research_cache: dict = {}


def _research():
    """One shared provider instance, so Tavily credit usage accumulates across requests."""
    if "r" not in _research_cache:
        try:
            _research_cache["r"] = (TavilyResearch(os.getenv("TAVILY_API_KEY", ""),
                                                   search_depth=os.getenv("TAVILY_SEARCH_DEPTH", "basic")), "tavily")
        except ResearchUnavailable:
            _research_cache["r"] = (MockResearch(), "mock (TAVILY_API_KEY not set; results are NOT live)")
    return _research_cache["r"]


def _gateway() -> ModelGateway:
    models = []
    if os.getenv("BIFROST_BASE_URL") and os.getenv("VERITYFORGE_MOCK_MODE", "true").lower() != "true":
        bf = BifrostProvider(os.environ["BIFROST_BASE_URL"], os.getenv("BIFROST_API_KEY", ""))
        # Models are '<provider>/<model>' as known to Bifrost; override via env for any configured provider.
        models += [ModelSpec(os.getenv("VERITYFORGE_SMALL_MODEL", "groq/openai/gpt-oss-20b"), bf, "small"),
                   ModelSpec(os.getenv("VERITYFORGE_LARGE_MODEL", "groq/openai/gpt-oss-120b"), bf, "large")]
        if os.getenv("VERITYFORGE_FALLBACK_MODEL"):  # a model on a DIFFERENT provider, for real failover
            models.append(ModelSpec(os.environ["VERITYFORGE_FALLBACK_MODEL"], bf, "small"))
        # Optional per-model pricing, USD per 1M tokens: VERITYFORGE_PRICING='{"groq/x":[input,output]}'
        for name, (p_in, p_out) in json.loads(os.getenv("VERITYFORGE_PRICING", "{}")).items():
            budget.pricing[name] = Pricing(float(p_in), float(p_out))
    else:
        models += [ModelSpec("mock-small", MockProvider(), "small"), ModelSpec("mock-large", MockProvider(), "large")]
    if os.getenv("LOCAL_MODEL_NAME"):
        models.append(ModelSpec(os.environ["LOCAL_MODEL_NAME"],
                                LocalProvider(os.getenv("LOCAL_MODEL_BASE_URL", "")), "small", local=True))
    return ModelGateway(models, budget)


gateway = _gateway()

# Route telemetry and audit events to the store (no-op for MemoryStore).
from .security import AUDIT  # noqa: E402

gateway.sink = store.record_request
AUDIT.sink = store.record_audit


def _sandbox_runner(ctx):
    from .sandbox import run_in_sandbox
    image = os.getenv("VERITYFORGE_SANDBOX_IMAGE", "python:3.12-slim")
    return lambda command, approval_id: run_in_sandbox(ctx, manager.gate, approval_id, image, command)


from fastapi import Depends, Header  # noqa: E402

from . import auth  # noqa: E402


def require_user(authorization: str | None = Header(default=None)) -> str:
    """Resolve the caller. Auth disabled (no secret/users configured) -> 'local'. Enabled -> valid token required."""
    if not auth.auth_enabled():
        return "local"
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "authentication required")
    try:
        return auth.verify_token(authorization.split(" ", 1)[1])
    except auth.AuthError as e:
        raise HTTPException(401, str(e))


class LoginIn(BaseModel):
    username: str
    password: str


@app.get("/api/v1/auth/status")
def auth_status():
    return {"auth_enabled": auth.auth_enabled(),
            "note": "When disabled (no secret/users configured), requests run as 'local' for development."}


@app.post("/api/v1/auth/login")
def login(body: LoginIn):
    if not auth.auth_enabled():
        raise HTTPException(400, "auth is disabled; configure VERITYFORGE_AUTH_SECRET and VERITYFORGE_USERS")
    from .security import AUDIT
    try:
        token = auth.authenticate(body.username, body.password)
    except auth.AuthError:
        AUDIT.record("login_failed", "warning", username=body.username)
        raise HTTPException(401, "invalid credentials")
    AUDIT.record("login_succeeded", "info", username=body.username)
    return {"token": token, "token_type": "bearer"}


from .tasks import TaskManager, make_router  # noqa: E402

manager = TaskManager(gateway, _sandbox_runner)
app.include_router(make_router(manager, require_user))


class VerifyIn(BaseModel):
    answer: str


class ContextIn(BaseModel):
    workspace_root: str
    task: str
    confidential: bool = False
    token_budget: int = 2000


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "research": _research()[1],
            "models": {m.name: {"provider": m.provider.name, "local": m.local,
                                "failures": gateway.health[m.name].failures} for m in gateway.models}}


@app.post("/api/v1/verify")
def verify(body: VerifyIn):
    research, mode = _research()
    live = any(m.provider.name != "mock" for m in gateway.models)
    judge = LLMJudge(gateway, SecurityContext("local", "verify", Scope.STANDARD, "")) if live else None
    rep = VerificationEngine(research, judge=judge).verify(body.answer)
    rep["research_provider"] = mode
    rep["claims"] = [{"claim": vars(r.claim), **{k: v for k, v in vars(r).items() if k != "claim"}}
                     for r in rep["claims"]]
    return rep


@app.post("/api/v1/context")
def context(body: ContextIn):
    ctx = SecurityContext("local", body.workspace_root, Scope.CONFIDENTIAL if body.confidential else Scope.STANDARD,
                          body.workspace_root)
    idx = RepoIndex(body.workspace_root)
    idx.build()
    c = idx.build_context(body.task, body.token_budget)
    return {**c, "scope": ctx.scope.value, "savings_pct": round(100 * (1 - c["tokens"] / max(c["full_repo_tokens"], 1)), 1),
            "note": "Token counts are character-based approximations, not provider-reported usage."}


@app.get("/api/v1/usage")
def usage():
    return {"requests": gateway.log, "daily_spend_estimated": budget.daily_spend,
            "warnings": budget.warnings, "note": "Costs are estimates from configured pricing."}


from pathlib import Path  # noqa: E402

_BENCH = Path(__file__).resolve().parents[3] / "benchmarks"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _plugin_registry():
    try:
        import sys
        for p in ("packages", "plugins"):
            root = str(Path(__file__).resolve().parents[3] / p)
            if root not in sys.path:
                sys.path.insert(0, root)
        from example_plugins import default_registry
        return default_registry()
    except Exception:  # noqa: BLE001 — plugins are optional; the app runs without them
        return None


_registry = _plugin_registry()


@app.get("/api/v1/plugins")
def plugins_list():
    """Extension registry: installed plugins, their declared permissions, grants, and enabled state."""
    if _registry is None:
        return {"available": False, "plugins": [], "note": "Plugin SDK not loaded."}
    from plugin_sdk import CONTRACT_VERSION
    return {"available": True, "contract_version": CONTRACT_VERSION, "plugins": _registry.list(),
            "note": "Plugins declare permissions; the host enforces them outside the plugin. A plugin cannot "
                    "self-grant access. Enable/disable and grants are managed here."}


class PluginToggleIn(BaseModel):
    enabled: bool


@app.post("/api/v1/plugins/{plugin_id}/enabled")
def plugin_toggle(plugin_id: str, body: PluginToggleIn, user: str = Depends(require_user)):
    if _registry is None:
        raise HTTPException(404, "plugin registry unavailable")
    from plugin_sdk import PluginError
    try:
        _registry.set_enabled(plugin_id, body.enabled)
    except PluginError as e:
        raise HTTPException(404, str(e))
    return {"id": plugin_id, "enabled": body.enabled}


class PluginRunIn(BaseModel):
    payload: dict


@app.post("/api/v1/plugins/{plugin_id}/run")
def plugin_run(plugin_id: str, body: PluginRunIn, user: str = Depends(require_user)):
    if _registry is None:
        raise HTTPException(404, "plugin registry unavailable")
    from plugin_sdk import PluginError
    try:
        return {"result": _registry.run(plugin_id, body.payload)}
    except PluginError as e:
        raise HTTPException(400, str(e))


@app.get("/api/v1/security")
def security():
    """Security & Permissions: active policy, sandbox limits, pending approvals, and the audit trail."""
    from .sandbox import SandboxLimits
    from .security import AUDIT, Action, READ_ONLY_ACTIONS
    lim = SandboxLimits()
    confidential_models = [m.name for m in gateway.models if m.local]
    pending = [{"id": p.req.id, "task_id": p.task_id, "action": p.req.action.value, "target": p.req.target,
                "impact": p.req.impact, "reason": p.req.reason, "detail": p.req.detail[:2000]}
               for p in manager.open_approvals()]
    return {
        "policy": {
            "read_only_actions": sorted(a.value for a in READ_ONLY_ACTIONS),
            "approval_required_actions": sorted(a.value for a in Action if a not in READ_ONLY_ACTIONS),
            "confidential_local_models": confidential_models,
            "confidential_fails_closed": len(confidential_models) == 0,
        },
        "sandbox": {"network": lim.network, "memory": lim.memory, "cpus": lim.cpus, "pids": lim.pids,
                    "timeout_s": lim.timeout_s, "read_only_root": True, "non_root_user": "65534:65534",
                    "capabilities": "ALL dropped"},
        "pending_approvals": pending,
        "audit": store.audit(100) or AUDIT.events(100),
        "note": "Approvals are bound to the exact operation (action+target+detail). Confidential repos never reach "
                "remote models/caches/logs and fail closed without a local model. Audit values are secret-redacted.",
    }


@app.get("/api/v1/evaluation")
def evaluation():
    """Evaluation Center: reads saved benchmark result files. Numbers are whatever was last measured and written
    by the benchmark scripts; nothing is recomputed or invented here. Missing files report 'not run yet'."""
    live_held = _read_json(_BENCH / "live" / "results_heldout_heldout-final.json")
    # dev progression: label -> judge accuracy, to show the fixes improving the pipeline
    dev_runs = []
    for f in sorted((_BENCH / "live").glob("results_dev_*.json")):
        d = _read_json(f)
        if d and "summary" in d:
            s = d["summary"]["judge"]
            dev_runs.append({"label": d.get("label", f.stem), "accuracy_overall": s.get("accuracy_overall"),
                             "accuracy_when_decided": s.get("accuracy_when_decided"), "coverage": s.get("coverage"),
                             "stale_passed_as_current": s.get("stale_passed_as_current_rate"),
                             "stale_recall": s.get("stale_detection_recall")})
    verification = _read_json(_BENCH / "verification" / "results.json")
    retrieval = _read_json(_BENCH / "retrieval" / "results.json")
    token_eff = _read_json(_BENCH / "token-efficiency" / "results.json")
    return {
        "live_verification": {
            "held_out": None if not live_held else {
                "gold_source": "endoflife.date API", "gold_fetched_on": live_held.get("gold_fetched_on"),
                "repeats": live_held.get("repeats"), "judge_model": "gemini-flash-lite-latest (via Bifrost)",
                "tavily_credits": live_held.get("tavily_credits_reported"),
                "summary": live_held["summary"]["judge"], "numeric_baseline": live_held["summary"]["numeric"],
                "per_claim": [{"claim": c["claim"], "gold": c["gold"], "statuses": c["statuses"],
                               "outcome": c["outcomes"][0]} for c in live_held["claims"]["judge"]]},
            "dev_progression": dev_runs,
            "note": "Held-out products never used during development. Small sample (12 time-sensitive claims x "
                    "repeats): indicative, not a precise rate. The safety-critical metric is "
                    "stale_passed_as_current (0.0 = no stale claim ever reported as current)."},
        "verification_offline": verification and {k: v for k, v in verification.items() if k != "failures"},
        "retrieval": retrieval,
        "token_efficiency": token_eff,
        "note": "All figures are read from saved benchmark result files (benchmarks/*/results*.json). Re-run the "
                "scripts to refresh. Synthetic datasets except the live held-out set, which uses independent gold.",
    }


@app.get("/api/v1/providers")
def providers():
    """Model & provider status: tier, scope, health, and configured pricing (not provider billing)."""
    live = any(m.provider.name != "mock" for m in gateway.models)
    out = []
    for m in gateway.models:
        h = gateway.health[m.name]
        p = budget.price_for(m.name)
        priced = m.name in budget.pricing
        out.append({"name": m.name, "provider": m.provider.name, "tier": m.tier, "local": m.local,
                    "consecutive_failures": h.failures, "circuit_open": h.open_until > __import__("time").monotonic(),
                    "pricing_configured": priced,
                    "price_input_per_m": p.input_per_m, "price_output_per_m": p.output_per_m})
    return {"mode": "live" if live else "mock", "research_provider": _research()[1], "models": out,
            "note": "Pricing is configured (VERITYFORGE_PRICING); unknown models use a conservative default, "
                    "never zero. These are estimates, not provider billing."}


@app.get("/api/v1/analytics")
def analytics():
    """Token & cost analytics. Merges persisted history (if a store is configured) with the current session."""
    # With a store, every request (including this session's) is persisted, so read from the store to get
    # the full cross-restart history. Without a store, fall back to the in-memory session log.
    persisted = store.requests(5000)
    log = persisted if persisted else gateway.log
    per_model: dict = {}
    for r in log:
        m = per_model.setdefault(r["model"], {"provider": r["provider"], "requests": 0, "input_tokens": 0,
                                              "output_tokens": 0, "estimated_cost": 0.0, "latency_sum": 0.0,
                                              "attempts": 0, "scopes": {}})
        m["requests"] += 1
        m["input_tokens"] += r["in"]
        m["output_tokens"] += r["out"]
        m["estimated_cost"] += r["cost"]
        m["latency_sum"] += r["latency"]
        m["attempts"] += r["attempts"]
        m["scopes"][r["scope"]] = m["scopes"].get(r["scope"], 0) + 1
    for m in per_model.values():
        m["avg_latency_s"] = round(m["latency_sum"] / m["requests"], 3) if m["requests"] else 0
        m["estimated_cost"] = round(m["estimated_cost"], 6)
        del m["latency_sum"]
    totals = {"requests": len(log), "input_tokens": sum(r["in"] for r in log),
              "output_tokens": sum(r["out"] for r in log),
              "estimated_cost": round(sum(r["cost"] for r in log), 6)}
    # Agent tasks: optimized context vs full-repo tokens, the token-saving story.
    tasks = []
    for t in manager.tasks.values():
        tasks.append({"id": t.id, "objective": t.objective, "state": t.state.value,
                      "input_tokens": t.usage.input_tokens, "output_tokens": t.usage.output_tokens,
                      "estimated_cost": round(t.usage.estimated_cost, 6), "model_calls": t.usage.model_calls})
    return {"totals": totals, "per_model": per_model, "tasks": tasks,
            "budget": {"daily_spend_estimated": round(budget.daily_spend, 6),
                       "daily_limit": budget.policy.daily, "monthly_limit": budget.policy.monthly,
                       "warnings": budget.warnings},
            "note": "Token counts are provider-reported where available; costs are estimates from configured "
                    "pricing, not provider billing."}


@app.exception_handler(PolicyViolation)
async def _pv(_, e):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=403, content={"error": "policy_violation", "detail": str(e)})


@app.exception_handler(BudgetExceeded)
async def _be(_, e):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=402, content={"error": "budget_exceeded", "detail": e.reason})
