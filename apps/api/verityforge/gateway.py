"""Provider-independent model gateway: Bifrost adapter, mock/local providers,
routing, health registry, bounded backoff failover. Business logic depends only
on ModelGateway, never on a concrete provider."""
from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

import httpx

from .budget import BudgetManager, estimate_cost
from .security import AUDIT, SecurityContext, check_remote_allowed, redact_secrets


class ProviderError(Exception):
    def __init__(self, msg: str, retryable: bool = True):
        super().__init__(msg)
        self.retryable = retryable


@dataclass
class ChatRequest:
    messages: list[dict]
    task_id: str = "adhoc"
    complexity: str = "low"  # low|medium|high
    max_output_tokens: int = 1024
    contains_repo_content: bool = False
    reasoning_effort: str | None = None  # "low"/"medium"/"high" for reasoning models; passed through if set


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass
class ChatResponse:
    text: str
    model: str
    provider: str
    usage: Usage
    estimated_cost: float
    latency_s: float
    attempts: int = 1
    fallback_used: bool = False
    notes: list[str] = field(default_factory=list)
    cost_is_estimate: bool = True


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _content_text(content) -> str:
    """OpenAI-compatible 'content' may be a string or a list of parts (Gemini via Bifrost). Join text parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") in (None, "text"))
    return ""


@dataclass
class ModelSpec:
    name: str
    provider: "ModelProvider"
    tier: str  # small|large
    local: bool = False


class ModelProvider(ABC):
    name = "provider"

    @abstractmethod
    def complete(self, model: str, req: ChatRequest) -> tuple[str, Usage]: ...


class BifrostProvider(ModelProvider):
    """Bifrost exposes an OpenAI-compatible HTTP API; models are addressed as
    '<provider>/<model>'. Live behavior is NOT verified in this repo without a key."""
    name = "bifrost"

    def __init__(self, base_url: str, api_key: str = "", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, model: str, req: ChatRequest) -> tuple[str, Usage]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": model, "messages": req.messages, "max_tokens": req.max_output_tokens}
        if req.reasoning_effort:
            payload["reasoning_effort"] = req.reasoning_effort
        try:
            r = httpx.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers, timeout=self.timeout)
        except httpx.TimeoutException as e:
            raise ProviderError(f"timeout: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"gateway error: {e}") from e
        if r.status_code == 429 or r.status_code >= 500:
            raise ProviderError(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            raise ProviderError(f"HTTP {r.status_code}: {redact_secrets(r.text[:200])}", retryable=False)
        try:
            data = r.json()
            u = data.get("usage", {})
            details = u.get("prompt_tokens_details") or {}
            choice = data["choices"][0]
            text = _content_text(choice["message"].get("content"))
            usage = Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0), details.get("cached_tokens", 0))
        except (KeyError, IndexError, ValueError, AttributeError) as e:
            raise ProviderError(f"invalid response: {e}") from e
        if not text.strip() and choice.get("finish_reason") == "length":
            # Reasoning models can spend the whole budget on hidden reasoning and return nothing.
            raise ProviderError(f"empty reply: max_output_tokens={req.max_output_tokens} exhausted before any "
                                "answer (reasoning model?); raise the limit", retryable=False)
        return text, usage


class MockProvider(ModelProvider):
    """Deterministic provider for tests/demos. Clearly labeled mock."""
    name = "mock"

    def __init__(self, responder: Callable[[str, ChatRequest], str] | None = None, fail_times: int = 0,
                 error: ProviderError | None = None):
        self.responder = responder or (lambda m, r: "ok")
        self.fail_times = fail_times
        self.error = error or ProviderError("simulated outage")
        self.calls = 0

    def complete(self, model: str, req: ChatRequest) -> tuple[str, Usage]:
        self.calls += 1
        if self.fail_times == -1 or self.calls <= self.fail_times:
            raise self.error
        text = self.responder(model, req)
        return text, Usage(sum(approx_tokens(m["content"]) for m in req.messages), approx_tokens(text))


class LocalProvider(BifrostProvider):
    """Local OpenAI-compatible backend (e.g. Ollama). Same wire format, local only."""
    name = "local"


@dataclass
class Health:
    failures: int = 0
    open_until: float = 0.0


class ModelGateway:
    def __init__(self, models: list[ModelSpec], budget: BudgetManager, max_retries: int = 2,
                 base_delay: float = 0.2, sleep: Callable[[float], None] = time.sleep):
        self.models = models
        self.budget = budget
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.sleep = sleep
        self.health: dict[str, Health] = {m.name: Health() for m in models}
        self.log: list[dict] = []  # request telemetry (no prompt content)
        self.sink: Callable[[dict], None] | None = None  # optional persistence hook (set by the API layer)

    def select(self, ctx: SecurityContext, req: ChatRequest) -> list[ModelSpec]:
        """Ordered candidates: security scope first, then complexity-based tier."""
        remote_blocked = ctx.confidential and req.contains_repo_content
        pool = [m for m in self.models if m.local] if remote_blocked else list(self.models)
        want = "large" if req.complexity == "high" else "small"
        now = time.monotonic()
        healthy = [m for m in pool if self.health[m.name].open_until <= now]
        healthy.sort(key=lambda m: (m.tier != want, m.local and not remote_blocked))
        return healthy

    def complete(self, ctx: SecurityContext, req: ChatRequest) -> ChatResponse:
        candidates = self.select(ctx, req)
        if not candidates:
            if ctx.confidential and req.contains_repo_content:
                # The most important block must be on the record: remote models were filtered out by policy.
                AUDIT.record("confidential_egress_blocked", "warning", user=ctx.user_id, repo=ctx.repo_id,
                             detail="No local model; confidential request refused (fail closed), nothing sent")
                raise ProviderError("No local model available; confidential task paused (fail closed).", False)
            raise ProviderError("No healthy model available; task paused.", False)
        t0 = time.monotonic()
        attempts, notes = 0, []
        for idx, spec in enumerate(candidates):
            if not spec.local:
                check_remote_allowed(ctx, req.contains_repo_content)
            in_est = sum(approx_tokens(m["content"]) for m in req.messages)
            projected = estimate_cost(self.budget.price_for(spec.name), in_est, req.max_output_tokens)
            self.budget.precheck(req.task_id, projected)  # raises BudgetExceeded before any call
            for attempt in range(self.max_retries + 1):
                attempts += 1
                try:
                    text, usage = spec.provider.complete(spec.name, req)
                except ProviderError as e:
                    h = self.health[spec.name]
                    h.failures += 1
                    notes.append(f"{spec.name} failed: {e}")
                    if not e.retryable:
                        break
                    if attempt < self.max_retries:
                        self.sleep(min(2.0, self.base_delay * 2 ** attempt) * random.uniform(0.5, 1.0))
                        continue
                    h.open_until = time.monotonic() + 30
                    break
                self.health[spec.name].failures = 0
                cost = estimate_cost(self.budget.price_for(spec.name), usage.input_tokens,
                                     usage.output_tokens, usage.cached_input_tokens)
                self.budget.record(req.task_id, cost)
                if idx > 0:
                    notes.append(f"Fell back to {spec.name} (tier={spec.tier}); quality/cost may differ.")
                lat = time.monotonic() - t0
                rec = {"task": req.task_id, "model": spec.name, "provider": spec.provider.name,
                       "in": usage.input_tokens, "out": usage.output_tokens, "cost": cost,
                       "latency": lat, "attempts": attempts, "scope": ctx.scope.value}
                self.log.append(rec)
                if self.sink:
                    try:
                        self.sink(rec)
                    except Exception:  # noqa: BLE001 — persistence must never break a model call
                        pass
                return ChatResponse(text, spec.name, spec.provider.name, usage, cost, lat, attempts, idx > 0, notes)
        raise ProviderError("All permitted models failed; task state preserved, paused. " + "; ".join(notes), False)
