"use client";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

function Card({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-cyan-300">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

const ACTIVE = new Set(["pending", "planning", "executing", "awaiting_approval", "testing"]);

export default function Dashboard() {
  const tasks = usePoll(api.tasks);
  const health = usePoll(api.health, 5000);
  const approvals = usePoll(api.approvals);

  if (tasks.error && !tasks.data)
    return <p role="alert" className="text-rose-300">API unreachable: {tasks.error}. Start it with uvicorn on port 8000.</p>;

  const list = tasks.data ?? [];
  const finished = list.filter((t) => t.state === "completed" || t.state === "failed");
  const completed = list.filter((t) => t.state === "completed").length;
  const tokens = list.reduce((s, t) => s + t.usage.total_tokens, 0);
  const cost = list.reduce((s, t) => s + t.usage.estimated_cost, 0);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Dashboard</h1>
      <p className="text-xs text-slate-500">
        Metrics cover tasks held in API memory since it started. Costs are estimates from configured pricing, not provider billing.
      </p>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card label="Active tasks" value={String(list.filter((t) => ACTIVE.has(t.state)).length)} />
        <Card label="Pending approvals" value={String(approvals.data?.length ?? 0)} />
        <Card label="Tokens consumed" value={tokens.toLocaleString()} hint="approximate (chars/4) unless provider-reported" />
        <Card label="Estimated cost" value={`$${cost.toFixed(6)}`} />
        <Card
          label="Completion rate"
          value={finished.length ? `${Math.round((100 * completed) / finished.length)}%` : "No data"}
          hint={`${completed} of ${finished.length} finished tasks verified by tests`}
        />
        <Card label="Tokens saved" value="No data" hint="needs a baseline run; see benchmarks/token-efficiency" />
        <Card label="Cache hit rate" value="No data" hint="not yet exposed by the API" />
        <Card label="Verification accuracy" value="No data" hint="requires the verification benchmark" />
      </div>
      <section aria-labelledby="ph">
        <h2 id="ph" className="mb-2 text-sm font-semibold text-slate-300">Provider health</h2>
        <ul className="space-y-1 text-sm">
          {Object.entries(health.data?.models ?? {}).map(([name, m]) => (
            <li key={name} className="flex gap-3">
              <span className="text-cyan-300">{name}</span>
              <span className="text-slate-400">{m.provider}{m.local ? " (local)" : ""}</span>
              <span className={m.failures ? "text-amber-300" : "text-emerald-300"}>{m.failures} consecutive failures</span>
            </li>
          ))}
        </ul>
        {health.data && <p className="mt-2 text-xs text-slate-500">Research provider: {health.data.research}</p>}
      </section>
      <section aria-labelledby="rt">
        <h2 id="rt" className="mb-2 text-sm font-semibold text-slate-300">Recent tasks</h2>
        {list.length === 0 && <p className="text-sm text-slate-500">No tasks yet.</p>}
        <ul className="space-y-1 text-sm">
          {[...list].reverse().slice(0, 8).map((t) => (
            <li key={t.id}>
              <span className="text-violet-300">{t.state}</span> — {t.objective}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
