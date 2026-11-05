"use client";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const OUTCOME: Record<string, { cls: string; label: string }> = {
  correct: { cls: "text-emerald-300", label: "correct" },
  wrong: { cls: "text-rose-300", label: "wrong" },
  abstain: { cls: "text-slate-400", label: "abstained" },
  missed: { cls: "text-amber-300", label: "missed" },
};

function Metric({ label, value, good, hint }: { label: string; value: string; good?: boolean; hint?: string }) {
  return (
    <div className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${good ? "text-emerald-300" : "text-cyan-300"}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export default function EvaluationPage() {
  const { data, error } = usePoll(api.evaluation, 10000);
  if (error && !data)
    return <p role="alert" className="text-rose-300">API unreachable: {error}.</p>;
  if (!data) return <p className="text-slate-400">Loading…</p>;

  const held = data.live_verification.held_out;
  const re = data.retrieval;
  const tok = data.token_efficiency;
  const vof = data.verification_offline as Record<string, number> | null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Evaluation Center</h1>
        <p className="mt-1 text-xs text-slate-500">{data.note}</p>
      </div>

      {/* Live verification, held-out */}
      <section aria-labelledby="live">
        <h2 id="live" className="mb-2 text-sm font-semibold text-slate-300">
          Live stale-answer detection — held-out set
        </h2>
        {!held ? (
          <p className="text-sm text-slate-500">No held-out result file yet. Run <code>benchmarks/live/run.py --set heldout</code>.</p>
        ) : (
          <>
            <p className="mb-3 text-xs text-slate-500">
              Gold: {held.gold_source} (fetched {held.gold_fetched_on}). Judge: {held.judge_model}. {held.repeats} repeats,{" "}
              {held.tavily_credits} Tavily credits. {data.live_verification.note}
            </p>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Metric label="Accuracy when decided" value={String(held.summary.accuracy_when_decided)}
                hint={`vs ${held.numeric_baseline.accuracy_when_decided} no-LLM baseline`} />
              <Metric label="Coverage" value={String(held.summary.coverage)} hint="share of claims decided (not abstained)" />
              <Metric label="Stale passed as current" value={String(held.summary.stale_passed_as_current_rate)}
                good={held.summary.stale_passed_as_current_rate === 0} hint="safety-critical — 0 is the goal" />
              <Metric label="False-alarm rate" value={String(held.summary.false_alarm_rate)}
                hint={`vs ${held.numeric_baseline.false_alarm_rate} baseline`} />
            </div>
            <table className="mt-4 w-full border-collapse text-sm">
              <caption className="sr-only">Per-claim held-out outcomes</caption>
              <thead>
                <tr className="border-b border-cyan-500/20 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th scope="col" className="py-2 pr-4">Claim</th>
                  <th scope="col" className="py-2 pr-4">Gold</th>
                  <th scope="col" className="py-2 pr-4">Outcome</th>
                  <th scope="col" className="py-2 pr-4">Statuses across repeats</th>
                </tr>
              </thead>
              <tbody>
                {held.per_claim.map((c, i) => {
                  const o = OUTCOME[c.outcome] ?? OUTCOME.abstain;
                  return (
                    <tr key={i} className="border-b border-navy-800">
                      <td className="py-2 pr-4 text-slate-200">{c.claim}</td>
                      <td className="py-2 pr-4 text-slate-400">{c.gold}</td>
                      <td className={`py-2 pr-4 font-medium ${o.cls}`}>{o.label}</td>
                      <td className="py-2 pr-4 text-xs text-slate-400">{c.statuses.join(", ")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </section>

      {/* Dev progression */}
      {data.live_verification.dev_progression.length > 0 && (
        <section aria-labelledby="dev">
          <h2 id="dev" className="mb-2 text-sm font-semibold text-slate-300">Dev-set progression (how fixes improved accuracy)</h2>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-cyan-500/20 text-left text-xs uppercase tracking-wide text-slate-400">
                <th scope="col" className="py-2 pr-4">Run</th>
                <th scope="col" className="py-2 pr-4">Acc. when decided</th>
                <th scope="col" className="py-2 pr-4">Coverage</th>
                <th scope="col" className="py-2 pr-4">Stale recall</th>
                <th scope="col" className="py-2 pr-4">Stale passed as current</th>
              </tr>
            </thead>
            <tbody>
              {data.live_verification.dev_progression.map((r) => (
                <tr key={r.label} className="border-b border-navy-800">
                  <td className="py-2 pr-4 font-mono text-cyan-300">{r.label}</td>
                  <td className="py-2 pr-4 text-slate-300">{r.accuracy_when_decided ?? "—"}</td>
                  <td className="py-2 pr-4 text-slate-300">{r.coverage ?? "—"}</td>
                  <td className="py-2 pr-4 text-slate-300">{r.stale_recall ?? "—"}</td>
                  <td className={`py-2 pr-4 ${r.stale_passed_as_current === 0 ? "text-emerald-300" : "text-rose-300"}`}>
                    {r.stale_passed_as_current ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Token efficiency */}
      <section aria-labelledby="tok">
        <h2 id="tok" className="mb-2 text-sm font-semibold text-slate-300">Token efficiency — optimized vs whole-repo baseline</h2>
        {!tok ? (
          <p className="text-sm text-slate-500">No result file. Run <code>benchmarks/token-efficiency/run.py</code>.</p>
        ) : (
          <>
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-cyan-500/20 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th scope="col" className="py-2 pr-4">Repo files</th>
                  <th scope="col" className="py-2 pr-4">Baseline input tokens</th>
                  <th scope="col" className="py-2 pr-4">Optimized</th>
                  <th scope="col" className="py-2 pr-4">Savings</th>
                </tr>
              </thead>
              <tbody>
                {tok.rows.map((r) => (
                  <tr key={r.repo_files} className="border-b border-navy-800">
                    <td className="py-2 pr-4 text-slate-300">{r.repo_files}</td>
                    <td className="py-2 pr-4 text-slate-300">{r.baseline_input.toLocaleString()}</td>
                    <td className="py-2 pr-4 text-slate-300">{r.optimized_input.toLocaleString()}</td>
                    <td className="py-2 pr-4 font-medium text-emerald-300">{r.savings_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-slate-500">{tok.note}</p>
          </>
        )}
      </section>

      {/* Offline benchmarks */}
      <section aria-labelledby="off" className="grid gap-4 md:grid-cols-2">
        <div>
          <h2 id="off" className="mb-2 text-sm font-semibold text-slate-300">Verification logic (synthetic)</h2>
          {!vof ? (
            <p className="text-sm text-slate-500">No result file.</p>
          ) : (
            <ul className="space-y-1 text-sm text-slate-300">
              {["status_accuracy", "stale_precision", "stale_recall", "false_positive_rate", "evidence_coverage"].map(
                (k) => (
                  <li key={k}>
                    <span className="text-slate-400">{k}:</span> {String(vof[k])}
                  </li>
                ),
              )}
            </ul>
          )}
        </div>
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-300">Code retrieval (synthetic)</h2>
          {!re ? (
            <p className="text-sm text-slate-500">No result file.</p>
          ) : (
            <ul className="space-y-1 text-sm text-slate-300">
              {Object.entries(re.systems).map(([name, m]) => (
                <li key={name}>
                  <span className="text-slate-400">{name}:</span> recall@3 {m["recall@3"]}, MRR {m["MRR@10"]}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
