"""VerityForge CLI — a thin client over the REST API. No business logic lives here.

Usage (API running on :8000, override with --api or VERITYFORGE_API_URL):
  vf health
  vf verify "An AI-generated answer to check"
  vf context <repo_path> "task description" [--confidential]
  vf task "objective" <repo_path> [--confidential] [--auto-approve] [--poll]
  vf approvals [--approve ID | --reject ID]
  vf analytics
  vf providers
  vf security
Exit codes: 0 ok, 1 error, 2 usage, 3 task ended not-completed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx

API = os.getenv("VERITYFORGE_API_URL", "http://localhost:8000").rstrip("/")
TERMINAL = {"completed", "failed", "cancelled"}


def _api() -> str:
    return API


def call(method: str, path: str, body: dict | None = None) -> dict:
    try:
        r = httpx.request(method, f"{_api()}/api/v1{path}", json=body, timeout=60)
    except httpx.HTTPError as e:
        print(f"error: cannot reach API at {_api()} ({e})", file=sys.stderr)
        raise SystemExit(1)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        print(f"error: HTTP {r.status_code}: {detail}", file=sys.stderr)
        raise SystemExit(1)
    return r.json() if r.content else {}


def _emit(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2))


def cmd_health(a) -> int:
    d = call("GET", "/health")
    _emit(d, a.json)
    if not a.json:
        print(f"status: {d['status']}  research: {d['research']}")
        for name, m in d["models"].items():
            print(f"  {name}  [{m['provider']}{'/local' if m['local'] else ''}]  failures={m['failures']}")
    return 0


def cmd_verify(a) -> int:
    d = call("POST", "/verify", {"answer": a.answer})
    _emit(d, a.json)
    if not a.json:
        print(f"research provider: {d['research_provider']}")
        for c in d["claims"]:
            print(f"\n[{c['status']}] {c['claim']['text']}  (score {c['score']}/100)")
            print(f"  why: {c['explanation']}")
            if c.get("correction"):
                print(f"  fix: {c['correction']}")
            for s in c["sources"][:4]:
                print(f"  - {s['url']} ({s.get('published_date') or 'date n/a'})")
    return 0


def cmd_context(a) -> int:
    d = call("POST", "/context", {"workspace_root": a.repo, "task": a.task, "confidential": a.confidential})
    _emit(d, a.json)
    if not a.json:
        print(f"relevant files: {', '.join(d['files'])}")
        print(f"context tokens: {d['tokens']} of {d['full_repo_tokens']} full-repo  (saved {d['savings_pct']}%)")
        print(d["note"])
    return 0


def cmd_task(a) -> int:
    t = call("POST", "/tasks", {"objective": a.objective, "workspace_root": a.repo, "confidential": a.confidential})
    tid = t["id"]
    print(f"task {tid} started (state={t['state']})")
    if not (a.poll or a.auto_approve):
        print("run 'vf approvals' to act on approval requests, 'vf task-status " + tid + "' to inspect")
        return 0
    last = None
    while True:
        t = call("GET", f"/tasks/{tid}")
        if t["state"] != last:
            print(f"  state: {t['state']}")
            last = t["state"]
        if a.auto_approve:
            for ap in call("GET", "/approvals"):
                if ap["task_id"] == tid:
                    print(f"  auto-approving {ap['action']} on {ap['target']}")
                    call("POST", f"/approvals/{ap['id']}/decision", {"approve": True})
        if t["state"] in TERMINAL:
            print(f"\noutcome: {t['outcome']}")
            u = t["usage"]
            print(f"model calls={u['model_calls']} tokens in/out={u['input_tokens']}/{u['output_tokens']} "
                  f"est_cost=${u['estimated_cost']:.6f}")
            for r in t["test_runs"]:
                print(f"  tests: {r['result']}")
            _emit(t, a.json)
            return 0 if t["state"] == "completed" else 3
        time.sleep(1.5)


def cmd_task_status(a) -> int:
    t = call("GET", f"/tasks/{a.id}")
    _emit(t, a.json)
    if not a.json:
        print(f"{t['id']}  {t['state']}  {t['objective']}")
        if t["outcome"]:
            print(f"  outcome: {t['outcome']}")
    return 0 if t["state"] == "completed" or t["state"] not in TERMINAL else 3


def cmd_approvals(a) -> int:
    if a.approve:
        call("POST", f"/approvals/{a.approve}/decision", {"approve": True})
        print(f"approved {a.approve}")
        return 0
    if a.reject:
        call("POST", f"/approvals/{a.reject}/decision", {"approve": False})
        print(f"rejected {a.reject}")
        return 0
    pending = call("GET", "/approvals")
    _emit(pending, a.json)
    if not a.json:
        if not pending:
            print("no pending approvals")
        for p in pending:
            print(f"{p['id']}  [{p['action']}] {p['target']}  (task {p['task_id']})")
            print(f"   reason: {p['reason']}")
    return 0


def cmd_simple(path):
    def run(a) -> int:
        d = call("GET", path)
        _emit(d, True if a.json else True)  # these are inherently structured; always pretty-print JSON
        return 0
    return run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vf", description="VerityForge CLI (thin client over the REST API)")
    p.add_argument("--api", help="API base URL (default $VERITYFORGE_API_URL or http://localhost:8000)")
    p.add_argument("--json", action="store_true", help="emit raw JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health").set_defaults(fn=cmd_health)

    v = sub.add_parser("verify")
    v.add_argument("answer")
    v.set_defaults(fn=cmd_verify)

    c = sub.add_parser("context")
    c.add_argument("repo")
    c.add_argument("task")
    c.add_argument("--confidential", action="store_true")
    c.set_defaults(fn=cmd_context)

    t = sub.add_parser("task")
    t.add_argument("objective")
    t.add_argument("repo")
    t.add_argument("--confidential", action="store_true")
    t.add_argument("--auto-approve", action="store_true", help="approve every request (demo/trusted repos only)")
    t.add_argument("--poll", action="store_true", help="wait for the task to finish")
    t.set_defaults(fn=cmd_task)

    ts = sub.add_parser("task-status")
    ts.add_argument("id")
    ts.set_defaults(fn=cmd_task_status)

    ap = sub.add_parser("approvals")
    ap.add_argument("--approve", metavar="ID")
    ap.add_argument("--reject", metavar="ID")
    ap.set_defaults(fn=cmd_approvals)

    for name in ("analytics", "providers", "security"):
        sub.add_parser(name).set_defaults(fn=cmd_simple(f"/{name}"))
    return p


def main(argv: list[str] | None = None) -> int:
    global API
    parser = build_parser()
    a = parser.parse_args(argv)
    if a.api:
        API = a.api.rstrip("/")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
