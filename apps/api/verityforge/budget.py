"""Backend-enforced budgets and pricing. Estimates are never presented as billing."""
from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Pricing:
    """USD per 1M tokens (configured, not provider billing)."""
    input_per_m: float
    output_per_m: float
    cached_input_per_m: float = 0.0


DEFAULT_PRICING: dict[str, Pricing] = {
    "mock-small": Pricing(0.10, 0.40, 0.01),
    "mock-large": Pricing(2.00, 8.00, 0.20),
    "local": Pricing(0.0, 0.0, 0.0),
}


def estimate_cost(pricing: Pricing, input_tokens: int, output_tokens: int, cached_input: int = 0) -> float:
    fresh = max(input_tokens - cached_input, 0)
    return (fresh * pricing.input_per_m + cached_input * pricing.cached_input_per_m
            + output_tokens * pricing.output_per_m) / 1_000_000


@dataclass
class BudgetPolicy:
    per_request: float = 1.0
    per_task: float = 5.0
    daily: float = 25.0
    monthly: float = 200.0
    warn_ratio: float = 0.8


@dataclass
class BudgetManager:
    policy: BudgetPolicy = field(default_factory=BudgetPolicy)
    pricing: dict[str, Pricing] = field(default_factory=lambda: dict(DEFAULT_PRICING))
    # Unknown models are priced conservatively (notional USD per 1M tokens), never at zero, so limits still bite.
    default_pricing: Pricing = Pricing(1.0, 3.0)
    task_spend: dict[str, float] = field(default_factory=dict)
    daily_spend: float = 0.0
    monthly_spend: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def price_for(self, model: str) -> Pricing:
        return self.pricing.get(model, self.default_pricing)

    def precheck(self, task_id: str, projected_cost: float) -> None:
        """Raise BudgetExceeded BEFORE a model call if any limit would be crossed."""
        p = self.policy
        spent = self.task_spend.get(task_id, 0.0)
        if projected_cost > p.per_request:
            raise BudgetExceeded(f"Request cost {projected_cost:.6f} exceeds per-request limit {p.per_request}")
        if spent + projected_cost > p.per_task:
            raise BudgetExceeded(f"Task spend would exceed per-task limit {p.per_task}")
        if self.daily_spend + projected_cost > p.daily:
            raise BudgetExceeded(f"Daily limit {p.daily} would be exceeded")
        if self.monthly_spend + projected_cost > p.monthly:
            raise BudgetExceeded(f"Monthly limit {p.monthly} would be exceeded")

    def record(self, task_id: str, cost: float) -> None:
        self.task_spend[task_id] = self.task_spend.get(task_id, 0.0) + cost
        self.daily_spend += cost
        self.monthly_spend += cost
        for name, spent, limit in (
            ("task", self.task_spend[task_id], self.policy.per_task),
            ("daily", self.daily_spend, self.policy.daily),
            ("monthly", self.monthly_spend, self.policy.monthly),
        ):
            if limit and spent >= limit * self.policy.warn_ratio:
                msg = f"{name} budget at {spent / limit:.0%}"
                if msg not in self.warnings:
                    self.warnings.append(msg)
