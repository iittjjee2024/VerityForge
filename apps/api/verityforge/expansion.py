"""LLM query expansion for code retrieval (bridges vocabulary mismatch). Degrades to no expansion on any failure."""
from __future__ import annotations

import json
import re

from .budget import BudgetExceeded
from .gateway import ChatRequest, ModelGateway, ProviderError
from .security import SecurityContext

SYSTEM = ('List up to 10 identifier-like keywords (function, class or variable names, lowercase words) that '
          'code implementing this task would likely contain. Reply ONLY with JSON: {"terms":[str]}.')


def expand_query(gw: ModelGateway, ctx: SecurityContext, task: str, task_id: str = "expand") -> list[str]:
    try:
        # For confidential repos the task text is treated as repo-derived, so it routes to local models only.
        r = gw.complete(ctx, ChatRequest([{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}],
                                         task_id=task_id, complexity="low", max_output_tokens=320,
                                         contains_repo_content=ctx.confidential, reasoning_effort="low"))
    except (ProviderError, BudgetExceeded):
        return []
    m = re.search(r"\{[\s\S]*\}", r.text)
    try:
        terms = json.loads(m.group(0)).get("terms", []) if m else []
    except (json.JSONDecodeError, AttributeError):
        return []
    # sanitize: model output is untrusted; keep only short identifier-like tokens
    return [t for t in terms if isinstance(t, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{2,30}", t)][:10]
