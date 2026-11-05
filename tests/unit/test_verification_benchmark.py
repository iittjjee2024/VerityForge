import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "verif_bench", Path(__file__).resolve().parents[2] / "benchmarks" / "verification" / "run.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_benchmark_regression_floor_and_known_gap():
    out = bench.evaluate()
    # floors on the synthetic set: guard against regressions, not evidence of real-world accuracy
    assert out["status_accuracy"] >= 0.93
    assert out["stale_recall"] >= 0.83
    assert out["false_positive_rate"] == 0.0
    # documented limitation: entity-level (leadership) comparison is unsupported without an LLM
    assert any(f[0] == "leadership-changed" for f in out["failures"])
