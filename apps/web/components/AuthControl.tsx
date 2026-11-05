"use client";
import { useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";

/** Shows a sign-in control only when the backend reports auth is enabled. Token lives in localStorage. */
export default function AuthControl() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const [open, setOpen] = useState(false);
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.authStatus().then((s) => setEnabled(s.auth_enabled)).catch(() => setEnabled(null));
    setSignedIn(!!getToken());
  }, []);

  if (enabled === null) return null; // API unknown/unreachable — stay quiet
  if (!enabled)
    return <span className="text-xs text-slate-500">auth disabled (local)</span>;

  if (signedIn)
    return (
      <button
        onClick={() => {
          setToken(null);
          setSignedIn(false);
        }}
        className="text-xs text-slate-300 hover:text-cyan-300"
      >
        sign out
      </button>
    );

  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)} className="text-xs text-amber-300 hover:text-amber-200">
        sign in
      </button>
      {open && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setErr(null);
            try {
              const { token } = await api.login(u, p);
              setToken(token);
              setSignedIn(true);
              setOpen(false);
            } catch (x) {
              setErr(x instanceof Error ? x.message : "login failed");
            }
          }}
          className="absolute right-0 z-10 mt-2 w-56 space-y-2 rounded border border-cyan-500/30 bg-navy-900 p-3 text-sm shadow-lg"
        >
          <input aria-label="username" value={u} onChange={(e) => setU(e.target.value)} placeholder="username"
            className="w-full rounded border border-slate-600 bg-navy-950 p-1.5" />
          <input aria-label="password" type="password" value={p} onChange={(e) => setP(e.target.value)} placeholder="password"
            className="w-full rounded border border-slate-600 bg-navy-950 p-1.5" />
          <button className="w-full rounded bg-cyan-600 py-1 text-white">Sign in</button>
          {err && <p className="text-xs text-rose-300">{err}</p>}
        </form>
      )}
    </div>
  );
}
