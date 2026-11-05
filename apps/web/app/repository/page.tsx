"use client";
import { useState } from "react";
import { api, type ContextResult } from "@/lib/api";

export default function RepositoryPage() {
  const [root, setRoot] = useState("");
  const [task, setTask] = useState("");
  const [confidential, setConfidential] = useState(false);
  const [res, setRes] = useState<ContextResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function explore(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      setRes(await api.buildContext({ workspace_root: root, task, confidential }));
    } catch (x) {
      setErr(x instanceof Error ? x.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Project Repository</h1>
      <p className="text-xs text-slate-500">
        Inspect how the agent builds a minimal, task-specific context from a repository — the token-optimization
        hierarchy (metadata → relevant files → symbol excerpts) rather than sending the whole repo.
      </p>

      <form onSubmit={explore} className="space-y-2 rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
        <label className="block text-sm">
          Repository path
          <input required value={root} onChange={(e) => setRoot(e.target.value)} placeholder="C:\path\to\repo"
            className="mt-1 w-full rounded border border-slate-600 bg-navy-900 p-2 text-sm" />
        </label>
        <label className="block text-sm">
          Task (drives relevance ranking)
          <input required value={task} onChange={(e) => setTask(e.target.value)} placeholder="add pagination to the product API"
            className="mt-1 w-full rounded border border-slate-600 bg-navy-900 p-2 text-sm" />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={confidential} onChange={(e) => setConfidential(e.target.checked)} />
          Confidential (local-only processing)
        </label>
        <button disabled={busy} className="rounded bg-gradient-to-r from-cyan-500 to-violet-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "Building…" : "Build context"}
        </button>
        {err && <p role="alert" className="text-sm text-rose-300">{err}</p>}
      </form>

      {res && (
        <section aria-label="Context result" className="space-y-4">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
              <div className="text-xs uppercase text-slate-400">Context tokens</div>
              <div className="mt-1 text-2xl font-semibold text-cyan-300">{res.tokens.toLocaleString()}</div>
            </div>
            <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
              <div className="text-xs uppercase text-slate-400">Full-repo tokens</div>
              <div className="mt-1 text-2xl font-semibold text-slate-300">{res.full_repo_tokens.toLocaleString()}</div>
            </div>
            <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
              <div className="text-xs uppercase text-slate-400">Tokens saved</div>
              <div className="mt-1 text-2xl font-semibold text-emerald-300">{res.savings_pct}%</div>
            </div>
            <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
              <div className="text-xs uppercase text-slate-400">Scope</div>
              <div className="mt-1 text-2xl font-semibold text-violet-300">{res.scope}</div>
            </div>
          </div>

          <div>
            <h2 className="mb-1 text-sm font-semibold text-slate-300">Relevant files ({res.files.length})</h2>
            <ul className="font-mono text-sm text-cyan-300">
              {res.files.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </div>

          {res.excerpts.length > 0 && (
            <div>
              <h2 className="mb-1 text-sm font-semibold text-slate-300">Selected symbol excerpts</h2>
              <ul className="text-sm text-slate-400">
                {res.excerpts.map(([file, line], i) => (
                  <li key={i}>
                    {file}:{line}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <details className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-3">
            <summary className="cursor-pointer text-sm text-slate-300">Assembled context sent to the model</summary>
            <pre className="mt-2 max-h-96 overflow-auto text-xs text-slate-400">{res.text}</pre>
          </details>
          <p className="text-xs text-slate-500">{res.note}</p>
        </section>
      )}
    </div>
  );
}
