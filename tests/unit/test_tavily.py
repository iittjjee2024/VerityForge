import httpx
import pytest

from verityforge.research import ResearchUnavailable, TavilyResearch
from verityforge.verification import VerificationEngine


def fake_post(capture, payload=None, status=200):
    def post(url, json=None, headers=None, timeout=None):
        capture.update(url=url, body=json, headers=headers)
        return httpx.Response(status, json=payload or {}, request=httpx.Request("POST", url))
    return post


OK = {"results": [
    {"url": "https://docs.libraryx.example/api", "title": "API", "content": "Current API version is 3.0.",
     "published_date": "2026-10-01", "score": 0.9},
    {"url": "https://x.example/undated", "title": "U", "content": "text", "published_date": None, "score": 0.1},
    {"title": "no url, must be dropped", "content": "x"}],
    "usage": {"credits": 1}}


def test_request_shape_and_response_parsing(monkeypatch):
    cap = {}
    monkeypatch.setattr(httpx, "post", fake_post(cap, OK))
    t = TavilyResearch("tvly-test")
    srcs = t.search("Library X latest API version")
    assert cap["url"] == "https://api.tavily.com/search"
    assert cap["headers"]["Authorization"] == "Bearer tvly-test"
    assert cap["body"]["include_published_date"] is True      # otherwise dates are never returned
    assert cap["body"]["search_depth"] == "basic"             # 1 credit, not 2
    assert [s.url for s in srcs] == ["https://docs.libraryx.example/api", "https://x.example/undated"]
    assert srcs[0].published_date == "2026-10-01" and srcs[1].published_date is None  # never invented
    assert t.credits_used == 1 and t.searches == 1


@pytest.mark.parametrize("status,hint", [(401, "invalid or missing"), (429, "rate limit"), (432, "credit limit")])
def test_http_errors_are_specific_and_not_treated_as_false(monkeypatch, status, hint):
    monkeypatch.setattr(httpx, "post", fake_post({}, {"detail": "x"}, status))
    with pytest.raises(ResearchUnavailable, match=hint):
        TavilyResearch("tvly-test").search("q")
    rep = VerificationEngine(TavilyResearch("tvly-test")).verify("Library X plan costs $19 per month.")
    assert rep["claims"][0].status == "Verification Failed"
    assert "Not treated as false" in rep["claims"][0].explanation


def test_network_failure_is_unavailable(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(ResearchUnavailable, match="ConnectError"):
        TavilyResearch("tvly-test").search("q")


def test_missing_key_raises():
    with pytest.raises(ResearchUnavailable):
        TavilyResearch("")


def test_end_to_end_with_tavily_shaped_response_marks_outdated_price(monkeypatch):
    payload = {"results": [{"url": "https://libraryx.example/pricing", "title": "Pricing",
                            "content": "Standard plan: $29 per month.", "published_date": "2026-10-15"}]}
    monkeypatch.setattr(httpx, "post", fake_post({}, payload))
    r = VerificationEngine(TavilyResearch("tvly-test")).verify("Library X standard plan costs $19 per month.")["claims"][0]
    assert r.status in ("Contradicted", "Potentially Stale") and "29" in r.correction
