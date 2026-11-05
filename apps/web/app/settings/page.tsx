"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function SettingsPage() {
  const { data, error } = usePoll(api.plugins, 4000);
  const [busy, setBusy] = useState<string | null>(null);

  async function toggle(id: string, enabled: boolean) {
    setBusy(id);
    try {
      await api.togglePlugin(id, enabled);
    } finally {
      setBusy(null);
    }
  }

  if (error && !data) return <p role="alert" className="text-rose-300">API unreachable: {error}.</p>;
  if (!data) return <p className="text-slate-400">Loading…</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Settings &amp; Extensions</h1>

      <section aria-labelledby="ext">
        <h2 id="ext" className="mb-2 text-sm font-semibold text-slate-300">
          Extension registry {data.contract_version && <span className="text-xs text-slate-500">(contract v{data.contract_version})</span>}
        </h2>
        {!data.available ? (
          <p className="text-sm text-slate-500">Plugin SDK not loaded.</p>
        ) : (
          <>
            <p className="mb-3 text-xs text-slate-500">{data.note}</p>
            <div className="space-y-3">
              {data.plugins.map((p) => (
                <div key={p.id} className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="font-semibold text-cyan-300">
                        {p.name} <span className="text-xs font-normal text-slate-500">v{p.version}</span>
                      </h3>
                      <p className="text-sm text-slate-300">{p.description}</p>
                    </div>
                    <button
                      onClick={() => toggle(p.id, !p.enabled)}
                      disabled={busy === p.id}
                      aria-pressed={p.enabled}
                      className={`rounded px-3 py-1 text-sm disabled:opacity-50 ${p.enabled ? "bg-emerald-600" : "bg-navy-700 text-slate-300"}`}
                    >
                      {p.enabled ? "Enabled" : "Disabled"}
                    </button>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-400">
                    <span>
                      permissions:{" "}
                      {p.permissions.length === 0 ? (
                        <span className="text-emerald-300">none</span>
                      ) : (
                        p.permissions.map((perm) => (
                          <span key={perm} className={p.granted.includes(perm) ? "text-emerald-300" : "text-amber-300"}>
                            {perm}
                            {p.granted.includes(perm) ? "✓ " : "(not granted) "}
                          </span>
                        ))
                      )}
                    </span>
                    {p.dependencies.length > 0 && <span>deps: {p.dependencies.join(", ")}</span>}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      <section aria-labelledby="cfg" className="rounded-lg border border-cyan-500/20 bg-navy-800/70 p-4 text-sm">
        <h2 id="cfg" className="mb-2 font-semibold text-slate-200">Configuration</h2>
        <p className="text-slate-400">
          Runtime configuration (models, pricing, budgets, persistence) is set via environment variables in <code>.env</code> and
          the Bifrost gateway config. See <code>docs/deployment</code>. Plugins add capabilities without changing core code;
          each declares the permissions it needs and the host enforces them outside the plugin.
        </p>
      </section>
    </div>
  );
}
