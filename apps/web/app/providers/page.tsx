"use client";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function ProvidersPage() {
  const { data, error } = usePoll(api.providers, 4000);

  if (error && !data)
    return <p role="alert" className="text-rose-300">API unreachable: {error}. Start it with uvicorn on port 8000.</p>;
  if (!data) return <p className="text-slate-400">Loading…</p>;

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Model &amp; Provider Management</h1>
        <span className={`rounded px-2 py-0.5 text-xs ${data.mode === "live" ? "bg-emerald-500/20 text-emerald-200" : "bg-amber-500/20 text-amber-200"}`}>
          {data.mode} mode
        </span>
      </div>
      <p className="text-xs text-slate-500">
        Requests route through the Bifrost gateway. Business logic never names a provider directly. Research provider: {data.research_provider}.
      </p>

      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Configured models and their status</caption>
        <thead>
          <tr className="border-b border-cyan-500/20 text-left text-xs uppercase tracking-wide text-slate-400">
            <th scope="col" className="py-2 pr-4">Model</th>
            <th scope="col" className="py-2 pr-4">Provider</th>
            <th scope="col" className="py-2 pr-4">Tier</th>
            <th scope="col" className="py-2 pr-4">Scope</th>
            <th scope="col" className="py-2 pr-4">Health</th>
            <th scope="col" className="py-2 pr-4">Price in / out ($/1M)</th>
          </tr>
        </thead>
        <tbody>
          {data.models.map((m) => (
            <tr key={m.name} className="border-b border-navy-800">
              <td className="py-2 pr-4 font-mono text-cyan-300">{m.name}</td>
              <td className="py-2 pr-4 text-slate-300">{m.provider}</td>
              <td className="py-2 pr-4 text-slate-300">{m.tier}</td>
              <td className="py-2 pr-4">{m.local ? <span className="text-violet-300">local only</span> : <span className="text-slate-400">remote</span>}</td>
              <td className="py-2 pr-4">
                {m.circuit_open ? (
                  <span className="text-rose-300">● circuit open</span>
                ) : m.consecutive_failures > 0 ? (
                  <span className="text-amber-300">● {m.consecutive_failures} recent failures</span>
                ) : (
                  <span className="text-emerald-300">● healthy</span>
                )}
              </td>
              <td className="py-2 pr-4 text-slate-300">
                {m.price_input_per_m} / {m.price_output_per_m}
                {!m.pricing_configured && <span className="ml-1 text-xs text-slate-500">(default)</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className="rounded-lg border border-cyan-500/20 bg-navy-800/60 p-4 text-sm text-slate-300">
        <h2 className="mb-2 font-semibold text-slate-200">How routing and failover work</h2>
        <ul className="list-disc space-y-1 pl-5 text-slate-400">
          <li>Task complexity picks the tier: small by default, larger on repair/high-risk work.</li>
          <li>On failure the gateway retries with bounded backoff, then fails over to the next healthy model.</li>
          <li>Confidential tasks never leave local models, and never fail over to a remote one — they fail closed.</li>
          <li>A model is skipped while its circuit is open; it re-enters after a cool-down.</li>
        </ul>
      </section>
      <p className="text-xs text-slate-500">{data.note}</p>
    </div>
  );
}
