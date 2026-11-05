"""Live evaluation: real Tavily evidence + real LLM judge (Groq via Bifrost) vs gold from endoflife.date.

Variants on IDENTICAL evidence:
  numeric : deterministic comparison only (no LLM)
  judge   : LLM judge first, numeric fallback; repeated --repeats times to measure run-to-run variance

Tavily results are recorded to evidence_cache_<set>.json and replayed, so variants/repeats cost no extra credits and
differ only in the LLM step. Usage (Bifrost running, keys in .env):
    python benchmarks/live/run.py --set dev --label baseline [--repeats 3] [--replay-only]
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).parent))
from verityforge.live import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from metrics import classify, summarize  # noqa: E402
from verityforge.budget import BudgetManager  # noqa: E402
from verityforge.gateway import BifrostProvider, ModelGateway, ModelSpec  # noqa: E402
from verityforge.judge import LLMJudge  # noqa: E402
from verityforge.research import ResearchProvider, ResearchUnavailable, Source, TavilyResearch  # noqa: E402
from verityforge.security import Scope, SecurityContext  # noqa: E402
from verityforge.verification import VerificationEngine  # noqa: E402


class RecordingResearch(ResearchProvider):
    """Records live Tavily results by query and replays them, so every variant sees identical evidence."""

    def __init__(self, path: Path, live: TavilyResearch | None):
        self.path, self.live = path, live
        self.cache = json.loads(path.read_text("utf-8")) if path.exists() else {}
        self.live_searches = 0

    def search(self, query: str, max_results: int = 5) -> list[Source]:
        if query not in self.cache:
            if self.live is None:
                raise ResearchUnavailable("replay-only: query not in evidence cache")
            srcs = self.live.search(query, max_results)
            self.cache[query] = {"retrieved_at": datetime.now(timezone.utc).isoformat(),
                                 "sources": [s.__dict__ for s in srcs]}
            self.path.write_text(json.dumps(self.cache, indent=1), "utf-8")
            self.live_searches += 1
        return [Source(**{k: v for k, v in s.items() if k != "official"}) for s in self.cache[query]["sources"]]


def run_variant(engine: VerificationEngine, items: list[dict], repeats: int, pace: float) -> list[dict]:
    rows = []
    for it in items:
        statuses, notes = [], []
        for _ in range(repeats):
            rep = engine.verify(it["claim"])
            res = rep["claims"]
            if not res:
                statuses.append("NO_CLAIM")
                notes.append("no claim extracted")
            else:
                statuses.append(res[0].status)
                notes.append(res[0].explanation[:160] + (f" | fix: {res[0].correction[:140]}" if res[0].correction else ""))
            if pace:
                time.sleep(pace)
        rows.append({"id": it["id"], "claim": it["claim"], "gold": it["gold"], "statuses": statuses,
                     "outcomes": [classify(it["gold"], s) for s in statuses], "notes": notes[0], "query": res[0].query if res else None})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["dev", "heldout"], required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--replay-only", action="store_true")
    a = ap.parse_args()

    data = json.loads((Path(__file__).parent / "dataset.json").read_text("utf-8"))
    items = data["sets"][a.set]
    live = None if a.replay_only else TavilyResearch(os.getenv("TAVILY_API_KEY", ""))
    research = RecordingResearch(Path(__file__).parent / f"evidence_cache_{a.set}.json", live)

    bf = BifrostProvider(os.environ["BIFROST_BASE_URL"], os.getenv("BIFROST_API_KEY", ""))
    judge_model = os.getenv("VERITYFORGE_JUDGE_MODEL", "gemini/gemini-flash-lite-latest")
    gw = ModelGateway([ModelSpec(judge_model, bf, "small")], BudgetManager(), max_retries=4, base_delay=2.0)
    judge = LLMJudge(gw, SecurityContext("eval", "verify", Scope.STANDARD, ""))
    print(f"judge model: {judge_model}")

    print(f"[{a.set}/{a.label}] {len(items)} claims, gold from {data['source']} fetched {data['fetched_on']}")
    numeric = run_variant(VerificationEngine(research), items, 1, 0)
    judged = run_variant(VerificationEngine(research, judge=judge), items, a.repeats,
                         float(os.getenv("EVAL_PACE_SECONDS", "6")))

    out = {"set": a.set, "label": a.label, "run_at": datetime.now(timezone.utc).isoformat(),
           "gold_fetched_on": data["fetched_on"], "repeats": a.repeats,
           "tavily_live_searches_this_run": research.live_searches,
           "tavily_credits_reported": getattr(live, "credits_used", 0),
           "judge_stats": judge.stats, "llm_requests": len(gw.log),
           "llm_tokens": {"input": sum(r["in"] for r in gw.log), "output": sum(r["out"] for r in gw.log)},
           "summary": {"numeric": summarize(numeric), "judge": summarize(judged)},
           "claims": {"numeric": numeric, "judge": judged}}
    path = Path(__file__).parent / f"results_{a.set}_{a.label}.json"
    path.write_text(json.dumps(out, indent=2), "utf-8")

    keys = ["correct", "wrong", "abstain", "missed", "accuracy_overall", "accuracy_when_decided", "coverage",
            "stale_passed_as_current_rate", "false_alarm_rate", "stale_detection_recall",
            "run_to_run_consistency", "controls_correct"]
    print(f"\n{'metric':<30}{'numeric':>12}{'judge':>12}")
    for k in keys:
        print(f"{k:<30}{str(out['summary']['numeric'][k]):>12}{str(out['summary']['judge'][k]):>12}")
    print(f"\njudge stats: {judge.stats}")
    print(f"live Tavily searches this run: {research.live_searches} (credits reported: {out['tavily_credits_reported']})")
    print(f"LLM: {out['llm_requests']} requests, tokens {out['llm_tokens']}")
    print("\nPer-claim (judge variant statuses across repeats):")
    for r in judged:
        mark = {"correct": "ok ", "wrong": "ERR", "abstain": "abs", "missed": "mis"}[r["outcomes"][0]]
        print(f" {mark} gold={r['gold']:<6} {r['claim'][:52]:<52} {r['statuses']}")
    print(f"\nresults written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
