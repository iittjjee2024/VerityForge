"use client";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-cyan-300">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

function Bar({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, (100 * used) / limit) : 0;
  const color = pct >= 80 ? "bg-rose-400" : pct >= 50 ? "bg-amber-400" : "bg-emerald-400";
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Daily budget utilisation"
      className="h-2 w-full overflow-hidden rounded bg-navy-700"
    >
      <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function AnalyticsPage() {
  const { data, error } = usePoll(api.analytics, 2000);

  if (error && !data)
    return <p role="alert" className="text-rose-300">API unreachable: {error}. Start it with uvicorn on port 8000.</p>;
  if (!data) return <p className="text-slate-400">Loading…</p>;

  const t = data.totals;
  const models = Object.entries(data.per_model);
  // Token saved: sum over tasks is not tracked server-side yet; show per-task optimized tokens instead.
  const taskTokens = data.tasks.reduce((s, x) => s + x.input_tokens + x.output_tokens, 0);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Token &amp; Cost Analytics</h1>
      <p className="text-xs text-slate-500">
        Aggregated from gateway requests since the API started. {data.note}
      </p>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Gateway requests" value={t.requests.toLocaleString()} />
        <Stat label="Input tokens" value={t.input_tokens.toLocaleString()} hint="provider-reported where available" />
        <Stat label="Output tokens" value={t.output_tokens.toLocaleString()} />
        <Stat label="Estimated cost" value={`$${t.estimated_cost.toFixed(6)}`} hint="configured pricing, not billing" />
      </div>

      <section aria-labelledby="budget">
        <h2 id="budget" className="mb-2 text-sm font-semibold text-slate-300">Daily budget</h2>
        <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
          <div className="mb-1 flex justify-between text-sm">
            <span className="text-slate-300">
              ${data.budget.daily_spend_estimated.toFixed(6)} of ${data.budget.daily_limit} (estimated)
            </span>
            <span className="text-slate-500">monthly limit ${data.budget.monthly_limit}</span>
          </div>
          <Bar used={data.budget.daily_spend_estimated} limit={data.budget.daily_limit} />
          {data.budget.warnings.length > 0 && (
            <ul className="mt-2 text-xs text-amber-300">
              {data.budget.warnings.map((w) => (
                <li key={w}>⚠ {w}</li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-slate-500">
            Limits are enforced in the backend before each model call, using tracked usage — not in this UI.
          </p>
        </div>
      </section>

      <section aria-labelledby="bymodel">
        <h2 id="bymodel" className="mb-2 text-sm font-semibold text-slate-300">By model</h2>
        {models.length === 0 ? (
          <p className="text-sm text-slate-500">No gateway requests recorded yet.</p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-cyan-500/20 text-left text-xs uppercase tracking-wide text-slate-400">
                <th scope="col" className="py-2 pr-4">Model</th>
                <th scope="col" className="py-2 pr-4">Requests</th>
                <th scope="col" className="py-2 pr-4">In / Out tokens</th>
                <th scope="col" className="py-2 pr-4">Avg latency</th>
                <th scope="col" className="py-2 pr-4">Est. cost</th>
                <th scope="col" className="py-2 pr-4">Scopes</th>
              </tr>
            </thead>
            <tbody>
              {models.map(([name, m]) => (
                <tr key={name} className="border-b border-navy-800">
                  <td className="py-2 pr-4 font-mono text-cyan-300">{name}</td>
                  <td className="py-2 pr-4 text-slate-300">{m.requests}</td>
                  <td className="py-2 pr-4 text-slate-300">
                    {m.input_tokens.toLocaleString()} / {m.output_tokens.toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 text-slate-300">{m.avg_latency_s}s</td>
                  <td className="py-2 pr-4 text-slate-300">${m.estimated_cost.toFixed(6)}</td>
                  <td className="py-2 pr-4 text-xs text-slate-400">
                    {Object.entries(m.scopes)
                      .map(([s, n]) => `${s}:${n}`)
                      .join(" ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="bytask">
        <h2 id="bytask" className="mb-2 text-sm font-semibold text-slate-300">
          By coding task ({taskTokens.toLocaleString()} tokens total)
        </h2>
        {data.tasks.length === 0 ? (
          <p className="text-sm text-slate-500">No coding tasks run yet.</p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-cyan-500/20 text-left text-xs uppercase tracking-wide text-slate-400">
                <th scope="col" className="py-2 pr-4">Task</th>
                <th scope="col" className="py-2 pr-4">State</th>
                <th scope="col" className="py-2 pr-4">Model calls</th>
                <th scope="col" className="py-2 pr-4">In / Out tokens</th>
                <th scope="col" className="py-2 pr-4">Est. cost</th>
              </tr>
            </thead>
            <tbody>
              {data.tasks.map((x) => (
                <tr key={x.id} className="border-b border-navy-800">
                  <td className="py-2 pr-4 text-slate-200">{x.objective}</td>
                  <td className="py-2 pr-4 text-violet-300">{x.state}</td>
                  <td className="py-2 pr-4 text-slate-300">{x.model_calls}</td>
                  <td className="py-2 pr-4 text-slate-300">
                    {x.input_tokens.toLocaleString()} / {x.output_tokens.toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 text-slate-300">${x.estimated_cost.toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-2 text-xs text-slate-500">
          For the optimized-vs-baseline token comparison, see <code>benchmarks/token-efficiency</code>.
        </p>
      </section>
    </div>
  );
}
