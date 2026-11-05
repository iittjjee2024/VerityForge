"""Web research providers. Tavily is the live provider; MockResearch is for tests only."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class ResearchUnavailable(Exception):
    pass


@dataclass
class Source:
    url: str
    title: str
    content: str
    published_date: str | None = None  # only when the provider supplies it
    score: float = 0.0
    official: bool = False  # set by the verifier when the domain matches the claim's subject

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.lower()


class ResearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[Source]: ...


_STATUS_HINT = {401: "invalid or missing Tavily API key", 403: "access forbidden", 429: "rate limit exceeded",
                432: "plan credit limit reached", 433: "pay-as-you-go limit reached"}


class TavilyResearch(ResearchProvider):
    """Tavily Search API (https://docs.tavily.com). 'basic' depth costs 1 credit, 'advanced' costs 2."""
    URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, timeout: float = 30.0, search_depth: str = "basic"):
        if not api_key:
            raise ResearchUnavailable("TAVILY_API_KEY not configured")
        self.api_key, self.timeout, self.search_depth = api_key, timeout, search_depth
        self.credits_used = 0.0  # as reported by Tavily (include_usage); not billing data
        self.searches = 0

    def search(self, query: str, max_results: int = 5) -> list[Source]:
        body = {"query": query, "max_results": max_results, "search_depth": self.search_depth,
                "topic": "general", "include_published_date": True, "include_usage": True}
        try:
            r = httpx.post(self.URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"},
                           timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            raise ResearchUnavailable(f"Tavily HTTP {code}: {_STATUS_HINT.get(code, 'request failed')}") from e
        except (httpx.HTTPError, ValueError) as e:
            raise ResearchUnavailable(f"Tavily request failed: {type(e).__name__}") from e
        self.searches += 1
        self.credits_used += float((data.get("usage") or {}).get("credits", 0) or 0)
        return [Source(url=x["url"], title=x.get("title", ""), content=x.get("content", ""),
                       published_date=x.get("published_date"), score=float(x.get("score", 0.0)))
                for x in results if x.get("url")]


class MockResearch(ResearchProvider):
    """Synthetic, clearly-labeled data for deterministic demos/tests."""
    def __init__(self, corpus: list[Source] | None = None, fail: bool = False):
        self.corpus, self.fail = corpus or [], fail

    def search(self, query: str, max_results: int = 5) -> list[Source]:
        if self.fail:
            raise ResearchUnavailable("mock outage")
        return self.corpus[:max_results]
