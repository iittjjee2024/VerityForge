"""Scoring for the live evaluation. Pure functions, unit-tested (tests/unit/test_live_metrics.py).

Outcome of one claim vs gold:
  correct   - status agrees with gold
  wrong     - status asserts the opposite (a false alarm on a true claim, or a stale claim passed as current)
  abstain   - Insufficient Evidence / Verification Failed (no assertion made; not counted as an error)
  missed    - Not Time-Sensitive on a claim that needed a live check, or the claim was not extracted
"""
from __future__ import annotations

from collections import Counter

STALE = {"Contradicted", "Potentially Stale"}
ABSTAIN = {"Insufficient Evidence", "Verification Failed"}


def classify(gold: str, status: str) -> str:
    if gold == "stable":
        return "correct" if status == "Not Time-Sensitive" else "wrong"
    if status in ABSTAIN:
        return "abstain"
    if status in ("Not Time-Sensitive", "NO_CLAIM"):
        return "missed"
    if gold == "true":
        return "correct" if status == "Verified Current" else "wrong"
    return "correct" if status in STALE else "wrong"  # gold == "false"


def _r(a: int, b: int):
    return round(a / b, 3) if b else None


def summarize(rows: list[dict]) -> dict:
    """rows: [{gold, outcomes: [outcome per repeat], statuses: [status per repeat]}] ; one entry per claim."""
    flat = [(r["gold"], o, s) for r in rows for o, s in zip(r["outcomes"], r["statuses"])]
    ts = [(g, o, s) for g, o, s in flat if g != "stable"]  # time-sensitive claims only
    c = Counter(o for _, o, _ in ts)
    n = len(ts)
    decided = c["correct"] + c["wrong"]
    false_claims = [(g, o) for g, o, _ in ts if g == "false"]
    true_claims = [(g, o) for g, o, _ in ts if g == "true"]
    consistent = sum(len(set(r["statuses"])) == 1 for r in rows)
    ctrl = [(o) for g, o, _ in flat if g == "stable"]
    return {
        "time_sensitive_claim_runs": n,
        "correct": c["correct"], "wrong": c["wrong"], "abstain": c["abstain"], "missed": c["missed"],
        "accuracy_overall": _r(c["correct"], n),
        "accuracy_when_decided": _r(c["correct"], decided),
        "coverage": _r(decided, n),
        # dangerous error: a stale/false claim passed as current
        "stale_passed_as_current_rate": _r(sum(o == "wrong" for _, o in false_claims), len(false_claims)),
        # nuisance error: a correct claim flagged stale
        "false_alarm_rate": _r(sum(o == "wrong" for _, o in true_claims), len(true_claims)),
        "stale_detection_recall": _r(sum(o == "correct" for _, o in false_claims), len(false_claims)),
        "run_to_run_consistency": _r(consistent, len(rows)),
        "controls_correct": f"{sum(o == 'correct' for o in ctrl)}/{len(ctrl)}",
    }
