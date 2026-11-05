"""Optimized vs baseline (whole-repo prompt) on identical tasks.

METHOD / LIMITS: the model is a SCRIPTED mock that returns the same correct patch in both modes, so this
measures prompt-size (input tokens, approximated as chars/4) and completion via real test execution.
It does NOT measure real-model correctness; rerun with live Bifrost models for that.
Usage: python benchmarks/token-efficiency/run.py [noise_files ...]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))
from verityforge.agent import AgentTask, CodingAgent  # noqa: E402
from verityforge.budget import BudgetManager  # noqa: E402
from verityforge.gateway import MockProvider, ModelGateway, ModelSpec  # noqa: E402
from verityforge.security import ApprovalGate, Scope, SecurityContext  # noqa: E402

SRC = "def list_products(items):\n    return items\n"
TEST = "from products import list_products\ndef test_p():\n    assert list_products([1,2,3], limit=2) == [1,2]\n"
REPLY = {"criteria": ["limit"], "plan": ["add limit"], "test_command": ["pytest"],
         "edits": [{"path": "products.py", "old": "def list_products(items):\n    return items",
                    "new": "def list_products(items, limit=None):\n    return items[:limit]"}]}


def pytest_runner(root):
    def run(cmd, aid):
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=root,
                           capture_output=True, text=True)
        return {"executed": True, "exit_code": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    return run


def make_gateway(live: bool):
    if live:  # real models through a local Bifrost; token counts are provider-reported
        from verityforge.gateway import BifrostProvider
        bf = BifrostProvider("http://127.0.0.1:8080")
        return ModelGateway([ModelSpec("groq/openai/gpt-oss-20b", bf, "small"),
                             ModelSpec("groq/openai/gpt-oss-120b", bf, "large")], BudgetManager(), sleep=__import__("time").sleep)
    prov = MockProvider(responder=lambda m, r: json.dumps(REPLY))
    return ModelGateway([ModelSpec("mock-small", prov, "small")], BudgetManager(), sleep=lambda s: None)


def run_once(noise: int, optimized: bool, live: bool = False) -> dict:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "products.py").write_text(SRC)
        (root / "test_products.py").write_text(TEST)
        for i in range(noise):
            (root / f"module_{i}.py").write_text("\n".join(f"def f{i}_{j}(x): return x + {j}" for j in range(60)))
        gw = make_gateway(live)
        ctx = SecurityContext("bench", "r", Scope.STANDARD, str(root))
        t = CodingAgent(gw, ApprovalGate(), pytest_runner(str(root)), lambda r: True,
                        optimized=optimized).run(AgentTask("add limit to list_products", ctx))
        return {"completed": t.state.value == "completed", "input_tokens": t.usage.input_tokens,
                "output_tokens": t.usage.output_tokens, "model_calls": t.usage.model_calls, "outcome": t.outcome}


def live_main(sizes, repeats):
    """Repeated live runs. Reports provider-reported input tokens, completion, and any failure outcome."""
    import statistics as st
    print(f"LIVE (Groq via Bifrost), {repeats} runs per cell. in = provider-reported input tokens")
    for n in sizes:
        row = {}
        for label, opt in (("baseline", False), ("optimized", True)):
            runs = [run_once(n, opt, live=True) for _ in range(repeats)]
            row[label] = runs
            ok = sum(r["completed"] for r in runs)
            ins = [r["input_tokens"] for r in runs if r["input_tokens"]]
            fails = sorted({r["outcome"][:70] for r in runs if not r["completed"]})
            print(f"  files={n + 2:>4} {label:>9}: completed {ok}/{repeats}  "
                  f"in(median)={int(st.median(ins)) if ins else 0:>6}  model_calls={[r['model_calls'] for r in runs]}  fails={fails}")
        b = [r["input_tokens"] for r in row["baseline"] if r["input_tokens"]]
        o = [r["input_tokens"] for r in row["optimized"] if r["input_tokens"]]
        if b and o:
            print(f"           token savings (median in): {100 * (1 - st.median(o) / st.median(b)):.1f}%")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sizes = [int(a) for a in args] or [10, 50, 200]
    if "--live" in sys.argv:
        live_main(sizes, repeats=3)
        sys.exit(0)
    print(f"{'repo files':>10} {'baseline in':>12} {'optimized in':>13} {'savings %':>10} {'base ok':>8} {'opt ok':>7}")
    rows = []
    for n in sizes:
        b, o = run_once(n, False), run_once(n, True)
        sav = 100 * (1 - o["input_tokens"] / b["input_tokens"])
        rows.append({"repo_files": n + 2, "baseline_input": b["input_tokens"], "optimized_input": o["input_tokens"],
                     "savings_pct": round(sav, 1), "baseline_completed": b["completed"], "optimized_completed": o["completed"]})
        print(f"{n + 2:>10} {b['input_tokens']:>12} {o['input_tokens']:>13} {sav:>10.1f} "
              f"{str(b['completed']):>8} {str(o['completed']):>7}")
    import json
    (Path(__file__).with_name("results.json")).write_text(
        json.dumps({"mode": "scripted", "rows": rows,
                    "note": "Scripted model: measures prompt-size reduction with real test execution, not real-model "
                            "correctness. See --live for provider-reported numbers."}, indent=2), "utf-8")
