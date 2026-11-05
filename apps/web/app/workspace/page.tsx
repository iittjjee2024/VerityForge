"use client";
import { useState } from "react";
import { api, type Task } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export default function Workspace() {
  const [objective, setObjective] = useState("");
  const [root, setRoot] = useState("");
  const [confidential, setConfidential] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const tasks = usePoll(api.tasks);
  const approvals = usePoll(api.approvals, 1000);

  const list = tasks.data ?? [];
  const current: Task | undefined = list.find((t) => t.id === selected) ?? list[list.length - 1];
  const pending = (approvals.data ?? []).filter((a) => a.task_id === current?.id);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const t = await api.createTask({ objective, workspace_root: root, confidential });
      setSelected(t.id);
      setObjective("");
    } catch (x) {
      setErr(x instanceof Error ? x.message : "failed");
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_1fr_24rem]">
      <aside aria-label="Task history" className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-3">
        <h2 className="mb-2 text-sm font-semibold">Task history</h2>
        <ul className="space-y-1 text-sm">
          {list.map((t) => (
            <li key={t.id}>
              <button onClick={() => setSelected(t.id)} className={`w-full truncate text-left hover:text-cyan-300 ${t.id === current?.id ? "text-cyan-300" : "text-slate-300"}`}>
                [{t.state}] {t.objective}
              </button>
            </li>
          ))}
        </ul>
        {current && (
          <>
            <h3 className="mb-1 mt-4 text-xs uppercase text-slate-400">Relevant files</h3>
            <ul className="text-xs text-slate-400">{current.relevant_files.slice(0, 15).map((f) => <li key={f}>{f}</li>)}</ul>
          </>
        )}
      </aside>

      <section aria-label="Task" className="space-y-4">
        <form onSubmit={submit} className="space-y-2 rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
          <label className="block text-sm">Repository path
            <input required value={root} onChange={(e) => setRoot(e.target.value)} className="mt-1 w-full rounded border border-slate-600 bg-navy-900 p-2 text-sm" placeholder="C:\path\to\repo" />
          </label>
          <label className="block text-sm">Task
            <textarea required value={objective} onChange={(e) => setObjective(e.target.value)} rows={3} className="mt-1 w-full rounded border border-slate-600 bg-navy-900 p-2 text-sm" placeholder="Add pagination to the product listing API" />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={confidential} onChange={(e) => setConfidential(e.target.checked)} />
            Confidential repository (local models only; fails closed)
          </label>
          <button className="rounded bg-gradient-to-r from-cyan-500 to-violet-500 px-4 py-2 text-sm font-medium text-white">Run task</button>
          {err && <p role="alert" className="text-sm text-rose-300">{err}</p>}
        </form>

        {current && (
          <div className="space-y-3 rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">{current.objective}</h2>
              <span className="rounded bg-violet-500/20 px-2 py-0.5 text-xs text-violet-200">{current.state}</span>
            </div>
            {current.outcome && <p className="text-sm text-amber-200">Outcome: {current.outcome}</p>}
            {current.plan.length > 0 && (
              <ol className="list-decimal pl-5 text-sm text-slate-300">{current.plan.map((p, i) => <li key={i}>{p}</li>)}</ol>
            )}
            <ul className="space-y-0.5 font-mono text-xs text-slate-500">{current.events.map((ev, i) => <li key={i}>{ev}</li>)}</ul>
            {!TERMINAL.has(current.state) && (
              <button onClick={() => api.cancel(current.id)} className="rounded border border-rose-400/50 px-3 py-1 text-sm text-rose-300">Cancel task</button>
            )}
          </div>
        )}
      </section>

      <aside aria-label="Details" className="space-y-4">
        {pending.map((a) => (
          <div key={a.id} role="group" aria-label="Approval request" className="rounded-lg border border-amber-400/40 bg-navy-800/80 p-3">
            <h2 className="text-sm font-semibold text-amber-200">Approval needed: {a.action}</h2>
            <p className="text-xs text-slate-400">Target: {a.target}</p>
            <p className="text-xs text-slate-400">Impact: {a.impact}</p>
            <p className="text-xs text-slate-400">Reason: {a.reason}</p>
            <pre className="my-2 max-h-64 overflow-auto rounded bg-navy-950 p-2 text-xs">{a.detail}</pre>
            <div className="flex gap-2">
              <button onClick={() => api.decide(a.id, true)} className="rounded bg-emerald-600 px-3 py-1 text-sm">Approve</button>
              <button onClick={() => api.decide(a.id, false)} className="rounded bg-rose-700 px-3 py-1 text-sm">Reject</button>
            </div>
          </div>
        ))}
        {current && (
          <>
            <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-3 text-sm">
              <h2 className="mb-1 font-semibold">Model usage</h2>
              <p>Calls: {current.usage.model_calls} · tool calls: {current.usage.tool_calls}</p>
              <p>Tokens in/out: {current.usage.input_tokens}/{current.usage.output_tokens} (approximate)</p>
              <p>Est. cost: ${current.usage.estimated_cost.toFixed(6)}</p>
              <p className="text-xs text-slate-500">Models: {current.usage.models.join(", ") || "none"}</p>
            </div>
            <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-3 text-sm">
              <h2 className="mb-1 font-semibold">Test results</h2>
              {current.test_runs.length === 0 && <p className="text-slate-500">Not executed</p>}
              {current.test_runs.map((r, i) => (
                <p key={i} className={r.result === "passed" ? "text-emerald-300" : r.result === "failed" ? "text-rose-300" : "text-amber-300"}>{r.result}: {r.command.join(" ")}</p>
              ))}
            </div>
            {current.diffs.map((d, i) => <pre key={i} className="max-h-64 overflow-auto rounded bg-navy-950 p-2 text-xs">{d}</pre>)}
          </>
        )}
      </aside>
    </div>
  );
}
