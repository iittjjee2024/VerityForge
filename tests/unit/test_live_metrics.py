import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "live_metrics", Path(__file__).resolve().parents[2] / "benchmarks" / "live" / "metrics.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_classify_truth_table():
    c = m.classify
    assert c("true", "Verified Current") == "correct"
    assert c("true", "Potentially Stale") == "wrong" and c("true", "Contradicted") == "wrong"
    assert c("false", "Contradicted") == "correct" and c("false", "Potentially Stale") == "correct"
    assert c("false", "Verified Current") == "wrong"          # stale claim passed as current
    for g in ("true", "false"):
        assert c(g, "Insufficient Evidence") == "abstain" and c(g, "Verification Failed") == "abstain"
        assert c(g, "Not Time-Sensitive") == "missed" and c(g, "NO_CLAIM") == "missed"
    assert c("stable", "Not Time-Sensitive") == "correct" and c("stable", "Verified Current") == "wrong"


def test_summarize_metrics():
    def row(g, st):
        return {"gold": g, "statuses": st, "outcomes": [m.classify(g, s) for s in st]}
    rows = [row("true", ["Verified Current"] * 3),            # correct x3
            row("true", ["Potentially Stale", "Verified Current", "Verified Current"]),  # 1 wrong, inconsistent
            row("false", ["Contradicted"] * 3),               # correct x3
            row("false", ["Verified Current"] * 3),           # stale passed as current x3
            row("false", ["Insufficient Evidence"] * 3),      # abstain x3
            row("stable", ["Not Time-Sensitive"] * 3)]
    s = m.summarize(rows)
    assert s["time_sensitive_claim_runs"] == 15
    assert (s["correct"], s["wrong"], s["abstain"], s["missed"]) == (8, 4, 3, 0)
    assert s["coverage"] == round(12 / 15, 3) and s["accuracy_when_decided"] == round(8 / 12, 3)
    assert s["stale_passed_as_current_rate"] == round(3 / 9, 3)
    assert s["false_alarm_rate"] == round(1 / 6, 3)
    assert s["stale_detection_recall"] == round(3 / 9, 3)
    assert s["run_to_run_consistency"] == round(5 / 6, 3)
    assert s["controls_correct"] == "3/3"
