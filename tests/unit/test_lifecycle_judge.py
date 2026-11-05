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
