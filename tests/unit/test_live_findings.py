"""Regression tests for problems found by the first live Tavily run."""
from datetime import datetime, timezone

from verityforge.research import MockResearch, Source
from verityforge.verification import VerificationEngine, build_query, extract_claims, parse_date, recency_score

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def test_rfc2822_dates_from_tavily_are_parsed():
    assert parse_date("Mon, 02 Nov 2026 00:00:00 GMT") == datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert parse_date("2026-10-01") is not None and parse_date("not a date") is None
    assert recency_score("Mon, 02 Nov 2026 00:00:00 GMT", 90, NOW) == 1.0   # fresh, no longer 'unknown'
    assert recency_score("Fri, 04 Oct 2024 07:57:00 GMT", 90, NOW) < 0.5     # genuinely old
    assert recency_score(None, 90, NOW) == 0.3 and recency_score("garbage", 90, NOW) == 0.3


def test_dotted_names_are_not_split_into_sentences():
    cl = extract_claims("Node.js 18 is the current LTS release of Node.js. Water boils at 100 degrees Celsius at sea level.")
    texts = [c.text for c in cl]
    assert "Node.js 18 is the current LTS release of Node.js" in texts
    assert "Node.js" in cl[0].entities
    q = build_query(cl[0])
    # Lifecycle claim: the version is the SUBJECT ("is Node.js 18 supported?"), so it must be in the query.
    # (Found in a demo rehearsal: without it, Tavily returned general Node.js pages that never mention v18.)
    assert cl[0].category == "lifecycle" and "Node.js 18" in q and "end of life" in q


def test_non_lifecycle_claims_still_strip_asserted_values():
    # "latest version is 3.9" ASSERTS 3.9; searching for "3.9" would bias results toward confirming it.
    v = extract_claims("Python 3.9 is the latest stable version of Python.")[0]
    assert v.category != "lifecycle" and "3.9" not in build_query(v)
    p = extract_claims("The Pro plan of Library X costs $19 per month.")[0]
    assert "19" not in build_query(p)


def test_lifecycle_query_names_exact_version_for_each_product():
    for text, want in [("PostgreSQL 12 is still supported.", "PostgreSQL 12"),
                       ("Python 3.12 is still supported.", "Python 3.12"),
                       ("Django 5.0 is still supported.", "Django 5.0")]:
        c = extract_claims(text)[0]
        assert c.category == "lifecycle" and want in build_query(c), (text, build_query(c))


def test_stable_fact_without_copula_is_extracted_and_not_researched():
    cl = extract_claims("Water boils at 100 degrees Celsius at sea level.")
    assert len(cl) == 1 and not cl[0].requires_verification
    rep = VerificationEngine(MockResearch(fail=True)).verify("Water boils at 100 degrees Celsius at sea level.")
    assert rep["claims"][0].status == "Not Time-Sensitive"


def test_instructions_and_short_fragments_are_not_claims():
    assert extract_claims("Install the package with pip first. Run the tests afterwards please.") == []


def test_official_domain_detection_is_not_spoofable():
    from verityforge.verification import mark_official, source_reliability
    mk = lambda u: Source(u, "t", "c")  # noqa: E731
    s = mark_official([mk("https://www.python.org/downloads"), mk("https://devguide.python.org/versions"),
                       mk("https://python.evil.com/x"), mk("https://www.mostlypython.com/a"),
                       mk("https://nodejs.org/en")], ["Python", "Node.js"])
    assert [x.official for x in s] == [True, True, False, False, True]
    assert source_reliability(s[0]) == 0.95 and source_reliability(s[2]) < 0.95


def test_entities_do_not_duplicate_in_search_query():
    c = extract_claims("Python 3.9 is the latest stable version of Python.")[0]
    assert "Python Python" not in build_query(c)


def test_version_index_page_is_not_evidence_either_way():
    index = Source("https://docs.example/index", "Docs",
                   "Versions: 2.6 2.7 3.0 3.1 3.2 3.3 3.4 3.5 3.6 3.7 3.8 3.9", "2026-11-02")
    r = VerificationEngine(MockResearch([index])).verify("Library X supports API version 3.9 today.")["claims"][0]
    assert r.status == "Insufficient Evidence" and not r.supporting and not r.contradicting


def test_single_value_page_still_counts():
    s = Source("https://docs.example/api", "API", "The current API version is 3.0.", "2026-11-02")
    r = VerificationEngine(MockResearch([s])).verify("Library X supports API version 2.4 today.")["claims"][0]
    assert r.status in ("Contradicted", "Potentially Stale") and r.contradicting


def test_query_uses_claim_wording_without_asserted_values():
    p = extract_claims("The Pro plan of Library X costs $19 per month.")[0]
    q = build_query(p)
    assert "19" not in q and "Library X" in q and "pricing" in q
    v = extract_claims("Python 3.9 is the latest stable version of Python.")[0]
    assert "3.9" not in build_query(v) and "latest stable version" in build_query(v)
