"use client";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const SEV: Record<string, string> = {
  info: "text-slate-300",
  warning: "text-amber-300",
  error: "text-rose-300",
};

function fmtTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString();
}

export default function SecurityPage() {
  const { data, error } = usePoll(api.security, 2000);

  async function decide(id: string, approve: boolean) {
    await api.decide(id, approve);
  }

  if (error && !data)
    return <p role="alert" className="text-rose-300">API unreachable: {error}.</p>;
  if (!data) return <p className="text-slate-400">Loading…</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Security &amp; Permissions</h1>
      <p className="text-xs text-slate-500">{data.note}</p>

      {/* Pending approvals — the live human-in-the-loop gate */}
      <section aria-labelledby="pending">
        <h2 id="pending" className="mb-2 text-sm font-semibold text-slate-300">
          Pending approvals ({data.pending_approvals.length})
        </h2>
        {data.pending_approvals.length === 0 ? (
          <p className="text-sm text-slate-500">No operations awaiting approval.</p>
        ) : (
          <div className="space-y-3">
            {data.pending_approvals.map((a) => (
              <div key={a.id} role="group" aria-label="Approval request" className="rounded-lg border border-amber-400/40 bg-navy-800/80 p-3">
                <h3 className="text-sm font-semibold text-amber-200">{a.action} → {a.target}</h3>
                <p className="text-xs text-slate-400">Impact: {a.impact}</p>
                <p className="text-xs text-slate-400">Reason: {a.reason}</p>
                <pre className="my-2 max-h-56 overflow-auto rounded bg-navy-950 p-2 text-xs">{a.detail}</pre>
                <div className="flex gap-2">
                  <button onClick={() => decide(a.id, true)} className="rounded bg-emerald-600 px-3 py-1 text-sm">Approve</button>
                  <button onClick={() => decide(a.id, false)} className="rounded bg-rose-700 px-3 py-1 text-sm">Reject</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Confidential policy */}
        <section aria-labelledby="conf" className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
          <h2 id="conf" className="mb-2 text-sm font-semibold text-slate-200">Confidential repository policy</h2>
          <ul className="space-y-1 text-sm text-slate-300">
            <li>No remote models, caches, logs, or web research for confidential repo content.</li>
            <li>
              Local models available:{" "}
              {data.policy.confidential_local_models.length > 0 ? (
                <span className="text-emerald-300">{data.policy.confidential_local_models.join(", ")}</span>
              ) : (
                <span className="text-amber-300">none configured</span>
              )}
            </li>
            <li>
              Fail-closed:{" "}
              <span className={data.policy.confidential_fails_closed ? "text-amber-300" : "text-emerald-300"}>
                {data.policy.confidential_fails_closed
                  ? "yes — confidential tasks pause (no local model)"
                  : "yes — confidential tasks route to a local model"}
              </span>
            </li>
            <li className="text-xs text-slate-500">Prompts cannot override this; it is enforced in backend code.</li>
          </ul>
        </section>

        {/* Sandbox */}
        <section aria-labelledby="sbx" className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
          <h2 id="sbx" className="mb-2 text-sm font-semibold text-slate-200">Code execution sandbox</h2>
          <ul className="space-y-1 text-sm text-slate-300">
            <li>Network: <span className="text-cyan-300">{data.sandbox.network}</span></li>
            <li>Memory / CPU / PIDs: {data.sandbox.memory} / {data.sandbox.cpus} / {data.sandbox.pids}</li>
            <li>Timeout: {data.sandbox.timeout_s}s</li>
            <li>Filesystem: read-only root, user {data.sandbox.non_root_user}</li>
            <li>Capabilities: {data.sandbox.capabilities}</li>
          </ul>
        </section>
      </div>

      {/* Permission model */}
      <section aria-labelledby="perm" className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
        <h2 id="perm" className="mb-2 text-sm font-semibold text-slate-200">Permission model</h2>
        <div className="grid gap-4 text-sm md:grid-cols-2">
          <div>
            <p className="mb-1 text-xs uppercase text-slate-400">Allowed without approval</p>
            <ul className="flex flex-wrap gap-2">
              {data.policy.read_only_actions.map((a) => (
                <li key={a} className="rounded bg-emerald-500/15 px-2 py-0.5 text-emerald-200">{a}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mb-1 text-xs uppercase text-slate-400">Require explicit approval</p>
            <ul className="flex flex-wrap gap-2">
              {data.policy.approval_required_actions.map((a) => (
                <li key={a} className="rounded bg-amber-500/15 px-2 py-0.5 text-amber-200">{a}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Audit trail */}
      <section aria-labelledby="audit">
        <h2 id="audit" className="mb-2 text-sm font-semibold text-slate-300">Audit trail (most recent first)</h2>
        {data.audit.length === 0 ? (
          <p className="text-sm text-slate-500">No security events recorded yet.</p>
        ) : (
          <ul className="space-y-1 font-mono text-xs">
            {data.audit.map((e, i) => (
              <li key={i} className="flex gap-3">
                <span className="text-slate-500">{fmtTime(e.ts)}</span>
                <span className={SEV[e.severity] ?? "text-slate-300"}>{e.event}</span>
                <span className="text-slate-400">
                  {Object.entries(e)
                    .filter(([k]) => !["ts", "event", "severity"].includes(k))
                    .map(([k, v]) => `${k}=${v}`)
                    .join(" ")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
