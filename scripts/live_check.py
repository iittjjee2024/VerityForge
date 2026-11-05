"""Live verification check: real Tavily search + (optionally) real LLM judge through Bifrost.

Usage (from repo root, with Bifrost running via scripts/start-bifrost.ps1):
    python scripts/live_check.py "Your AI-generated answer text here"
Reads keys from .env. Prints evidence exactly as retrieved; nothing is invented or hard-coded.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from verityforge.live import load_dotenv  # noqa: E402

load_dotenv(Path(".env"))

from verityforge.budget import BudgetManager  # noqa: E402
from verityforge.gateway import BifrostProvider, ModelGateway, ModelSpec  # noqa: E402
from verityforge.judge import LLMJudge  # noqa: E402
from verityforge.research import ResearchUnavailable, TavilyResearch  # noqa: E402
from verityforge.security import Scope, SecurityContext  # noqa: E402
from verityforge.verification import VerificationEngine  # noqa: E402


def main(answer: str) -> int:
    try:
        tavily = TavilyResearch(os.getenv("TAVILY_API_KEY", ""), search_depth=os.getenv("TAVILY_SEARCH_DEPTH", "basic"))
    except ResearchUnavailable as e:
        print(f"Cannot run live check: {e}. Add TAVILY_API_KEY to .env.")
        return 2
    judge = None
    if os.getenv("BIFROST_BASE_URL") and os.getenv("VERITYFORGE_MOCK_MODE", "true").lower() != "true":
        bf = BifrostProvider(os.environ["BIFROST_BASE_URL"], os.getenv("BIFROST_API_KEY", ""))
        gw = ModelGateway([ModelSpec(os.getenv("VERITYFORGE_SMALL_MODEL", "groq/openai/gpt-oss-20b"), bf, "small")],
                          BudgetManager())
        judge = LLMJudge(gw, SecurityContext("live", "verify", Scope.STANDARD, ""))
    rep = VerificationEngine(tavily, judge=judge).verify(answer)
    print(f"LLM judge: {'on' if judge else 'off'} | claims: {len(rep['claims'])}\n")
    for r in rep["claims"]:
        print(f"[{r.status}] {r.claim.text!r}  ({r.claim.category}, indicator {r.score}/100)")
        print(f"   query: {r.query}\n   why:   {r.explanation}")
        if r.correction:
            print(f"   fix:   {r.correction}")
        for s in r.sources:
            tag = "supports" if s["url"] in r.supporting else "contradicts" if s["url"] in r.contradicting else ""
            print(f"   - {s['url']}  date={s['published_date'] or 'unavailable'}  reliability={s['reliability']} {tag}")
        print()
    print(f"Tavily: {tavily.searches} search(es), {tavily.credits_used} credit(s) reported by the API")
    return 0


if __name__ == "__main__":
    sys.exit(main(" ".join(sys.argv[1:]) or "Python 3.9 is the latest stable version of Python."))
