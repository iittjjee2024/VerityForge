export type Usage = {
  model_calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  models: string[];
};

export type Task = {
  id: string;
  objective: string;
  state: string;
  outcome: string;
  scope: string;
  plan: string[];
  acceptance_criteria: string[];
  relevant_files: string[];
  diffs: string[];
  test_runs: { command: string[]; result: string }[];
  repairs: number;
  events: string[];
  usage: Usage;
};

export type Approval = {
  id: string;
  task_id: string;
  action: string;
  target: string;
  detail: string;
  impact: string;
  reason: string;
};

export type ClaimView = {
  claim: { id: string; text: string; category: string; freshness_class: string; start: number; end: number };
  status: string;
  score: number;
  explanation: string;
  score_breakdown: Record<string, number>;
  sources: { url: string; title: string; published_date: string | null; reliability: number }[];
  supporting: string[];
  contradicting: string[];
  conflicting_sources: boolean;
  correction: string | null;
  query: string | null;
};

export type VerifyReport = {
  answer: string;
  claims: ClaimView[];
  summary: Record<string, number>;
  research_provider: string;
  note: string;
};

export type Health = {
  status: string;
  research: string;
  models: Record<string, { provider: string; local: boolean; failures: number }>;
};

export type ProviderModel = {
  name: string;
  provider: string;
  tier: string;
  local: boolean;
  consecutive_failures: number;
  circuit_open: boolean;
  pricing_configured: boolean;
  price_input_per_m: number;
  price_output_per_m: number;
};

export type Providers = {
  mode: string;
  research_provider: string;
  models: ProviderModel[];
  note: string;
};

export type Analytics = {
  totals: { requests: number; input_tokens: number; output_tokens: number; estimated_cost: number };
  per_model: Record<
    string,
    {
      provider: string;
      requests: number;
      input_tokens: number;
      output_tokens: number;
      estimated_cost: number;
      avg_latency_s: number;
      attempts: number;
      scopes: Record<string, number>;
    }
  >;
  tasks: {
    id: string;
    objective: string;
    state: string;
    input_tokens: number;
    output_tokens: number;
    estimated_cost: number;
    model_calls: number;
  }[];
  budget: {
    daily_spend_estimated: number;
    daily_limit: number;
    monthly_limit: number;
    warnings: string[];
  };
  note: string;
};

export type LiveSummary = {
  accuracy_overall: number;
  accuracy_when_decided: number;
  coverage: number;
  stale_passed_as_current_rate: number;
  false_alarm_rate: number;
  stale_detection_recall: number;
  run_to_run_consistency: number;
  controls_correct: string;
  correct: number;
  wrong: number;
  abstain: number;
  missed: number;
};

export type Evaluation = {
  live_verification: {
    held_out: {
      gold_source: string;
      gold_fetched_on: string;
      repeats: number;
      judge_model: string;
      tavily_credits: number;
      summary: LiveSummary;
      numeric_baseline: LiveSummary;
      per_claim: { claim: string; gold: string; statuses: string[]; outcome: string }[];
    } | null;
    dev_progression: {
      label: string;
      accuracy_overall: number | null;
      accuracy_when_decided: number | null;
      coverage: number | null;
      stale_passed_as_current: number | null;
      stale_recall: number | null;
    }[];
    note: string;
  };
  verification_offline: Record<string, number | string | object> | null;
  retrieval: { queries: number; systems: Record<string, { "recall@3": number; "MRR@10": number }> } | null;
  token_efficiency: {
    mode: string;
    rows: { repo_files: number; baseline_input: number; optimized_input: number; savings_pct: number }[];
    note: string;
  } | null;
  note: string;
};

export type Security = {
  policy: {
    read_only_actions: string[];
    approval_required_actions: string[];
    confidential_local_models: string[];
    confidential_fails_closed: boolean;
  };
  sandbox: {
    network: string;
    memory: string;
    cpus: string;
    pids: number;
    timeout_s: number;
    read_only_root: boolean;
    non_root_user: string;
    capabilities: string;
  };
  pending_approvals: {
    id: string;
    task_id: string;
    action: string;
    target: string;
    impact: string;
    reason: string;
    detail: string;
  }[];
  audit: { ts: number; event: string; severity: string; [k: string]: unknown }[];
  note: string;
};

export type Plugins = {
  available: boolean;
  contract_version?: string;
  plugins: {
    id: string;
    name: string;
    version: string;
    description: string;
    contract_version: string;
    permissions: string[];
    granted: string[];
    enabled: boolean;
    dependencies: string[];
  }[];
  note: string;
};

export type ContextResult = {
  text: string;
  tokens: number;
  files: string[];
  excerpts: [string, number][];
  full_repo_tokens: number;
  scope: string;
  savings_pct: number;
  note: string;
};

const TOKEN_KEY = "vf_token";

export function getToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null) {
  if (typeof window === "undefined") return;
  if (t) window.localStorage.setItem(TOKEN_KEY, t);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(`/api/v1${path}`, { ...init, headers, cache: "no-store" });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    if (r.status === 401) throw new Error("authentication required — sign in");
    throw new Error(body.detail ?? `HTTP ${r.status}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => call<Health>("/health"),
  tasks: () => call<Task[]>("/tasks"),
  task: (id: string) => call<Task>(`/tasks/${id}`),
  createTask: (b: { objective: string; workspace_root: string; confidential: boolean }) =>
    call<Task>("/tasks", { method: "POST", body: JSON.stringify(b) }),
  cancel: (id: string) => call<unknown>(`/tasks/${id}/cancel`, { method: "POST" }),
  approvals: () => call<Approval[]>("/approvals"),
  decide: (id: string, approve: boolean) =>
    call<unknown>(`/approvals/${id}/decision`, { method: "POST", body: JSON.stringify({ approve }) }),
  verify: (answer: string) => call<VerifyReport>("/verify", { method: "POST", body: JSON.stringify({ answer }) }),
  providers: () => call<Providers>("/providers"),
  analytics: () => call<Analytics>("/analytics"),
  evaluation: () => call<Evaluation>("/evaluation"),
  security: () => call<Security>("/security"),
  authStatus: () => call<{ auth_enabled: boolean; note: string }>("/auth/status"),
  login: (username: string, password: string) =>
    call<{ token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  plugins: () => call<Plugins>("/plugins"),
  togglePlugin: (id: string, enabled: boolean) =>
    call<unknown>(`/plugins/${id}/enabled`, { method: "POST", body: JSON.stringify({ enabled }) }),
  buildContext: (b: { workspace_root: string; task: string; confidential: boolean }) =>
    call<ContextResult>("/context", { method: "POST", body: JSON.stringify(b) }),
};
