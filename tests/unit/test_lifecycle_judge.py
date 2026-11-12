import json
from datetime import date

import pytest

from verityforge.budget import BudgetManager
from verityforge.gateway import MockProvider, ModelGateway, ModelSpec
from verityforge.judge import LLMJudge
from verityforge.research import MockResearch, Source
from verityforge.security import Scope, SecurityContext
from verityforge.verification import VerificationEngine

TODAY = date(2026, 11, 4)
PG = Source("https://endoflife.date/postgresql", "PostgreSQL EOL",
            "PostgreSQL 15 released 2022-10-13, end of life 2027-11-11. "
            "PostgreSQL 12 reached end of life 2024-11-14.", "2026-10-01")
CTX = SecurityContext("u", "verify", Scope.STANDARD, "")


def judge_with(reply):
    prov = MockProvider(responder=lambda m, r: reply if isinstance(reply, str) else json.dumps(reply))
    gw = ModelGateway([ModelSpec("mock-small", prov, "small")], BudgetManager(), sleep=lambda s: None)
    return LLMJudge(gw, CTX), prov


def test_extract_eol_future_date_is_supported():
    j, _ = judge_with({"eol_date": "2027-11-11", "source_url": PG.url,
                       "quote": "PostgreSQL 15 released 2022-10-13, end of life 2027-11-11."})
    v = j.extract_eol("PostgreSQL 15", [PG], today=TODAY)
    assert v["stance"] == "supports" and v["two_step"] and v["eol_date"] == "2027-11-11"


def test_extract_eol_past_date_is_not_supported():
    j, _ = judge_with({"eol_date": "2024-11-14", "source_url": PG.url,
                       "quote": "PostgreSQL 12 reached end of life 2024-11-14."})
    v = j.extract_eol("PostgreSQL 12", [PG], today=TODAY)
    assert v["stance"] == "contradicts" and v["eol_date"] == "2024-11-14"


def test_extract_eol_none_means_supported():
    s = Source("https://ex.example/x", "x", "Product Z has no planned end-of-life and is supported indefinitely.", None)
    j, _ = judge_with({"eol_date": "none", "source_url": s.url,
                       "quote": "Product Z has no planned end-of-life and is supported indefinitely."})
    assert j.extract_eol("Product Z", [s], today=TODAY)["stance"] == "supports"


def test_extract_eol_unknown_falls_back():
    j, _ = judge_with({"eol_date": "unknown", "source_url": PG.url,
                       "quote": "PostgreSQL 15 released 2022-10-13, end of life 2027-11-11."})
    assert j.extract_eol("PostgreSQL 15", [PG], today=TODAY) is None


def test_extract_eol_accepts_non_iso_date_format_in_source():
    # endoflife.date renders dates as "11 Nov 2027"; the model normalises to ISO. Must still be accepted.
    s = Source("https://endoflife.date/postgresql", "PG",
               "| 15 | 4 years ago (13 Oct 2022) | Ends in 1 year (11 Nov 2027) | 15.19 |", "2026-10-01")
    j, _ = judge_with({"eol_date": "2027-11-11", "source_url": s.url,
                       "quote": "| 15 | 4 years ago (13 Oct 2022) | Ends in 1 year (11 Nov 2027) | 15.19 |"})
    v = j.extract_eol("PostgreSQL 15", [s], today=TODAY)
    assert v is not None and v["stance"] == "supports"


def test_extract_eol_hallucinated_date_not_in_source_is_rejected():
    j, _ = judge_with({"eol_date": "2099-01-01", "source_url": PG.url,
                       "quote": "PostgreSQL 15 released 2022-10-13, end of life 2027-11-11."})
    # model claims 2099 but that date is nowhere in the quote/source -> rejected, not trusted
    assert j.extract_eol("PostgreSQL 15", [PG], today=TODAY) is None


def test_extract_eol_year_month_only():
    s = Source("https://ex.example/p", "p", "Python 3.11 security end 2027-10.", "2026-01-01")
    j, _ = judge_with({"eol_date": "2027-10", "source_url": s.url, "quote": "Python 3.11 security end 2027-10."})
    assert j.extract_eol("Python 3.11", [s], today=TODAY)["stance"] == "supports"


def test_engine_routes_lifecycle_claims_to_two_step():
    j, prov = judge_with({"eol_date": "2027-11-11", "source_url": PG.url,
                          "quote": "PostgreSQL 15 released 2022-10-13, end of life 2027-11-11."})
    r = VerificationEngine(MockResearch([PG]), judge=j).verify("PostgreSQL 15 is still supported.")["claims"][0]
    assert r.claim.category == "lifecycle"
    assert r.status == "Verified Current" and "Two-step lifecycle check" in r.explanation
    assert prov.calls == 1


def test_engine_past_eol_lifecycle_is_contradicted_with_correction():
    j, _ = judge_with({"eol_date": "2024-11-14", "source_url": PG.url,
                       "quote": "PostgreSQL 12 reached end of life 2024-11-14."})
    r = VerificationEngine(MockResearch([PG]), judge=j).verify("PostgreSQL 12 is still supported.")["claims"][0]
    assert r.status == "Contradicted" and "end-of-life" in r.correction


# ---- found in a demo rehearsal: nodejs.org says "Node.js 18 ... are End-Of-Life" but gives no date -----------
NODE = Source("https://nodejs.org/en/blog/announcements/node-18-eol-support", "Node 18 EOL",
              "Node.js 18 and all earlier versions are End-Of-Life. They are now completely unsupported.", None)
NODE_QUOTE = "Node.js 18 and all earlier versions are End-Of-Life. They are now completely unsupported."


def test_date_supplied_from_memory_is_rejected():
    # The model "knows" 2025-04-30, but the evidence never says it -> must not be trusted.
    j, _ = judge_with({"eol_date": "2025-04-30", "source_url": NODE.url, "quote": NODE_QUOTE})
    assert j.extract_eol("Node.js 18 is still supported", [NODE], today=TODAY) is None


def test_explicit_end_of_life_without_date_is_accepted_as_ended():
    j, _ = judge_with({"eol_date": "ended", "source_url": NODE.url, "quote": NODE_QUOTE})
    v = j.extract_eol("Node.js 18 is the current LTS release of Node.js", [NODE], today=TODAY)
    assert v is not None and v["stance"] == "contradicts" and v["eol_date"] == "ended"


def test_ended_requires_the_exact_version_in_the_quote():
    s = Source("https://ex.example/n", "n", "Node.js 16 is End-Of-Life and unsupported.", None)
    j, _ = judge_with({"eol_date": "ended", "source_url": s.url, "quote": "Node.js 16 is End-Of-Life and unsupported."})
    # claim is about 18, quote is about 16 -> reject (and "16" must not match inside "160" etc.)
    assert j.extract_eol("Node.js 18 is still supported", [s], today=TODAY) is None


def test_ended_requires_explicit_end_of_life_wording():
    s = Source("https://ex.example/n", "n", "Node.js 18 was released with many new features for developers.", None)
    j, _ = judge_with({"eol_date": "ended", "source_url": s.url,
                       "quote": "Node.js 18 was released with many new features for developers."})
    assert j.extract_eol("Node.js 18 is still supported", [s], today=TODAY) is None


def test_engine_reports_ended_verdict_with_cited_correction():
    j, _ = judge_with({"eol_date": "ended", "source_url": NODE.url, "quote": NODE_QUOTE})
    r = VerificationEngine(MockResearch([NODE]), judge=j).verify(
        "Node.js 18 is the current LTS release of Node.js.")["claims"][0]
    assert r.status == "Contradicted" and "no date given" in r.explanation
    assert r.correction.startswith("Reached end-of-life; source https://nodejs.org")


def test_us_and_ordinal_date_formats_are_recognised():
    """Found in a demo rehearsal: aws.amazon.com writes 'reached end of life on April 30, 2025'; the US
    'Month D, YYYY' form was missing, so a correct, quoted date was rejected as unsupported."""
    from verityforge.judge import _date_in_text
    d = date(2025, 4, 30)
    for text in ("reached end of life on April 30, 2025", "on April 30th, 2025", "Apr 30 2025",
                 "30th April 2025", "30 Apr 2025", "2025-04-30", "April 2025"):
        assert _date_in_text(d, text), text
    assert not _date_in_text(d, "reached end of life on April 3, 2025")   # a different day must not match
    assert not _date_in_text(d, "April 30, 2024")                         # nor a different year


def test_aws_style_quote_is_accepted_end_to_end():
    s = Source("https://aws.amazon.com/blogs/devops/node18", "AWS",
               "AWS CDK will no longer support Node.js 18.x, which reached end of life on April 30, 2025.", None)
    j, _ = judge_with({"eol_date": "2025-04-30", "source_url": s.url,
                       "quote": "AWS CDK will no longer support Node.js 18.x, which reached end of life on April 30, 2025."})
    v = j.extract_eol("Node.js 18 is the current LTS release of Node.js", [s], today=TODAY)
    assert v is not None and v["stance"] == "contradicts" and v["eol_date"] == "2025-04-30"
