"""Scenario A: efficient coding agent, end to end through the REST API.

Task: "Add pagination to the product listing API, update the frontend, and add tests."
Flow: copy demo repo to a scratch dir -> show context/token preview -> start task -> print every approval
(exact diff / command) -> approve -> tests run in the Docker sandbox -> report outcome + REAL token usage.

Needs: API running (live mode), Bifrost running, Docker up, sandbox image built:
    docker build -t verityforge-sandbox sandbox/    (and VERITYFORGE_SANDBOX_IMAGE=verityforge-sandbox)
Usage: python demo/scenario_a.py [--api http://localhost:8000] [--manual]
  --manual : do not auto-approve; approve in the UI / CLI yourself (for the recorded demo)
"""
import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

import httpx

# Model output can contain characters the Windows console codepage can't encode (e.g. U+2011); never crash on print.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

TASK = "Add pagination to the product listing API, update the frontend, and add tests."
SRC = Path(__file__).parent / "products_repo"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--manual", action="store_true")
    ap.add_argument("--timeout", type=int, default=420)
    a = ap.parse_args()
    B = a.api.rstrip("/") + "/api/v1"

    work = Path(tempfile.mkdtemp(prefix="vf_demo_")) / "products_repo"
    shutil.copytree(SRC, work, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    print(f"scratch repo: {work}\n")

    ctx = httpx.post(f"{B}/context", json={"workspace_root": str(work), "task": TASK}, timeout=60).json()
    print("== Step 1: minimal context (no whole-repo upload)")
    print(f"   relevant files : {', '.join(ctx['files'])}")
    print(f"   context tokens : {ctx['tokens']}  vs whole repo {ctx['full_repo_tokens']}  "
          f"-> {ctx['savings_pct']}% fewer (approximate, chars/4)\n")

    t = httpx.post(f"{B}/tasks", json={"objective": TASK, "workspace_root": str(work)}, timeout=60)
    t.raise_for_status()
    tid = t.json()["id"]
    print(f"== Step 2: task {tid} started\n")

    seen, deadline, last = set(), time.time() + a.timeout, None
    while time.time() < deadline:
        task = httpx.get(f"{B}/tasks/{tid}", timeout=30).json()
        if task["state"] != last:
            print(f"   state -> {task['state']}")
            last = task["state"]
        for ap_ in httpx.get(f"{B}/approvals", params={"task_id": tid}, timeout=30).json():
            if ap_["id"] in seen:
                continue
            seen.add(ap_["id"])
            print(f"\n   APPROVAL NEEDED [{ap_['action']}] {ap_['target']}\n   impact: {ap_['impact']}")
            print("   " + ap_["detail"][:1400].replace("\n", "\n   "))
            if a.manual:
                print("   (waiting for you to approve in the UI/CLI...)")
            else:
                httpx.post(f"{B}/approvals/{ap_['id']}/decision", json={"approve": True}, timeout=30)
                print("   -> auto-approved (demo mode)\n")
        if task["state"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(2)
    else:
        print("timed out")
        return 2

    u = task["usage"]
    print("\n== Result")
    print(f"   state   : {task['state']}   outcome: {task['outcome']}")
    print(f"   tests   : {[r['result'] for r in task['test_runs']]}   repairs: {task['repairs']}")
    print(f"   models  : {u['models']}")
    print(f"   usage   : {u['model_calls']} model call(s), tokens in/out = {u['input_tokens']}/{u['output_tokens']} "
          f"(provider-reported), est. cost ${u['estimated_cost']:.6f} (estimate, not billing)")
    print(f"\n   final api.py:\n" + "\n".join("     " + l for l in (work / "shop" / "api.py").read_text().splitlines()))
    new_tests = sorted(p.name for p in (work / "tests").glob("*.py"))
    print(f"\n   test files now: {new_tests}")
    return 0 if task["state"] == "completed" else 3


if __name__ == "__main__":
    sys.exit(main())
