"""Verification benchmark on a SYNTHETIC dataset (see dataset.json).

Reports claim-extraction precision/recall, stale-claim detection precision/recall, FP/FN rates, status
accuracy, evidence coverage and a coarse score-calibration table. Research is mocked per case, so this
measures the extraction/comparison/scoring logic, NOT live Tavily retrieval quality or real-world accuracy.
Usage: python benchmarks/verification/run.py [--verbose]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))
from verityforge.research import MockResearch, Source  # noqa: E402
from verityforge.verification import VerificationEngine  # noqa: E402

POSITIVE = {"Contradicted", "Potentially Stale"}  # "stale/outdated" class


def evaluate(path: Path | None = None) -> dict:
    data = json.loads((path or Path(__file__).with_name("dataset.json")).read_text("utf-8"))
    tp_pred = n_pred = tp_gold = n_gold = 0
    matched = []  # (gold, result)
    misses = []
    for case in data["cases"]:
        corpus = [Source(**s) for s in case["sources"]]
        rep = VerificationEngine(MockResearch(corpus, fail=case.get("research_fails", False))).verify(case["answer"])
        results = rep["claims"]
        used = set()
        for g in case["gold"]:
            n_gold += 1
            hit = next((i for i, r in enumerate(results) if i not in used and g["contains"].lower() in r.claim.text.lower()), None)
            if hit is None:
                misses.append((case["id"], "claim not extracted", g["contains"]))
                continue
            used.add(hit)
            tp_gold += 1
            matched.append((case["id"], g, results[hit]))
        n_pred += len(results)
        tp_pred += len(used)
        for i, r in enumerate(results):
            if i not in used:
                misses.append((case["id"], "spurious claim", r.claim.text))

    correct = [(cid, g, r) for cid, g, r in matched if r.status in g["status"]]
    for cid, g, r in matched:
        if r.status not in g["status"]:
            misses.append((cid, f"status {r.status!r} not in {g['status']}", r.claim.text))
    gold_pos = [(c, g, r) for c, g, r in matched if set(g["status"]) <= POSITIVE]
    gold_neg = [(c, g, r) for c, g, r in matched if not (set(g["status"]) & POSITIVE)]
    tp = sum(r.status in POSITIVE for _, _, r in gold_pos)
    fn = len(gold_pos) - tp
    fp = sum(r.status in POSITIVE for _, _, r in gold_neg)
    pred_pos = tp + fp
    needs = [r for _, _, r in matched if r.claim.requires_verification and r.status != "Verification Failed"]
    cal = {"score<60": [0, 0], "score>=60": [0, 0]}
    for _, g, r in matched:
        if r.score and r.claim.requires_verification:
            b = cal["score>=60" if r.score >= 60 else "score<60"]
            b[0] += 1
            b[1] += r.status in g["status"]

    def ratio(a, b):
        return round(a / b, 3) if b else None

    return {
        "cases": len(data["cases"]), "gold_claims": n_gold,
        "extraction_precision": ratio(tp_pred, n_pred), "extraction_recall": ratio(tp_gold, n_gold),
        "status_accuracy": ratio(len(correct), len(matched)),
        "stale_precision": ratio(tp, pred_pos), "stale_recall": ratio(tp, len(gold_pos)),
        "false_positive_rate": ratio(fp, len(gold_neg)), "false_negative_rate": ratio(fn, len(gold_pos)),
        "evidence_coverage": ratio(sum(bool(r.sources) for r in needs), len(needs)),
        "calibration": {k: {"n": v[0], "status_accuracy": ratio(v[1], v[0])} for k, v in cal.items()},
        "failures": misses,
    }


if __name__ == "__main__":
    out = evaluate()
    # Persist a machine-readable summary so the Evaluation Center can display real numbers (no re-run per request).
    (Path(__file__).with_name("results.json")).write_text(json.dumps(out, indent=2), "utf-8")
    fails = out.pop("failures")
    print(json.dumps(out, indent=2))
    print(f"\n{len(fails)} failure(s):")
    for f in fails:
        print("  -", *f)
