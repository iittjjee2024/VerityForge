"""Exact-match cache. Keys bind model, prompt version, context hash and security scope."""
from __future__ import annotations

import hashlib
import json
import time

from .security import SecurityContext


class ScopedCache:
    def __init__(self, ttl_s: int = 3600):
        self.ttl, self._d, self.hits, self.misses = ttl_s, {}, 0, 0

    @staticmethod
    def key(ctx: SecurityContext, model: str, prompt_version: str, context_hash: str, tool_cfg: str = "") -> str:
        raw = json.dumps([ctx.cache_namespace(), model, prompt_version, context_hash, tool_cfg])
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, ctx: SecurityContext, key: str):
        if ctx.confidential:  # confidential results never enter shared caches
            return None
        v = self._d.get(key)
        if v and v[0] > time.time():
            self.hits += 1
            return v[1]
        self.misses += 1
        return None

    def put(self, ctx: SecurityContext, key: str, value) -> None:
        if not ctx.confidential:
            self._d[key] = (time.time() + self.ttl, value)
