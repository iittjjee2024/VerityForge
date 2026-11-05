"use client";
import { useState } from "react";
import { api, type VerifyReport } from "@/lib/api";

// Status is conveyed by text AND color/symbol, never color alone.
const STYLE: Record<string, { cls: string; icon: string }> = {
  "Verified Current": { cls: "border-emerald-400/50 text-emerald-300", icon: "✔" },
  "Potentially Stale": { cls: "border-amber-400/50 text-amber-300", icon: "⏳" },
  Contradicted: { cls: "border-rose-400/50 text-rose-300", icon: "✖" },
  "Insufficient Evidence": { cls: "border-slate-400/50 text-slate-300", icon: "?" },
  "Not Time-Sensitive": { cls: "border-cyan-400/40 text-cyan-300", icon: "∞" },
  "Verification Failed": { cls: "border-fuchsia-400/50 text-fuchsia-300", icon: "!" },
};

export default function Verify() {
  const [answer, setAnswer] = useState("");
  const [report, setReport] = useState<VerifyReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      setReport(await api.verify(answer));
    } catch (x) {
      setErr(x instanceof Error ? x.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Answer Verification</h1>
      <form onSubmit={run} className="space-y-2">
        <label className="block text-sm">AI-generated answer
          <textarea required value={answer} onChange={(e) => setAnswer(e.target.value)} rows={5} className="mt-1 w-full rounded border border-slate-600 bg-navy-900 p-2 text-sm" />
        </label>
        <button disabled={busy} className="rounded bg-gradient-to-r from-cyan-500 to-violet-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{busy ? "Verifying…" : "Verify claims"}</button>
      </form>
      {err && <p role="alert" className="text-rose-300">{err}</p>}
      {report && (
        <section aria-label="Report" className="space-y-3">
          <p className="text-xs text-slate-500">Research provider: {report.research_provider}. {report.note}</p>
          <p className="text-sm">{Object.entries(report.summary).map(([k, v]) => `${k}: ${v}`).join(" · ") || "No verifiable claims found."}</p>
          {report.claims.map((c) => {
            const s = STYLE[c.status] ?? STYLE["Insufficient Evidence"];
            return (
              <article key={c.claim.id} className={`rounded-lg border bg-navy-800/70 p-4 ${s.cls}`}>
                <div className="flex items-start justify-between gap-4">
                  <p className="text-slate-100">“{c.claim.text}”</p>
                  <span className="whitespace-nowrap font-semibold">{s.icon} {c.status}</span>
                </div>
                <p className="mt-1 text-xs text-slate-400">{c.claim.category} · {c.claim.freshness_class} · system freshness indicator: {c.score}/100 (not a probability)</p>
                <p className="mt-2 text-sm text-slate-200">{c.explanation}</p>
                {c.correction && <p className="mt-1 text-sm text-emerald-300">Suggested correction: {c.correction}</p>}
                {c.conflicting_sources && <p className="mt-1 text-sm text-amber-300">Sources conflict; both sides are listed below.</p>}
                <ul className="mt-2 space-y-1 text-xs">
                  {c.sources.map((src) => (
                    <li key={src.url}>
                      <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-cyan-300 underline">{src.title || src.url}</a>
                      {" · "}{src.published_date ?? "date unavailable"} · reliability {src.reliability}
                      {c.supporting.includes(src.url) && " · supports"}
                      {c.contradicting.includes(src.url) && " · contradicts"}
                    </li>
                  ))}
                </ul>
                {Object.keys(c.score_breakdown).length > 0 && (
                  <p className="mt-2 text-xs text-slate-500">Score components: {Object.entries(c.score_breakdown).map(([k, v]) => `${k} ${v}`).join(", ")}</p>
                )}
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}
