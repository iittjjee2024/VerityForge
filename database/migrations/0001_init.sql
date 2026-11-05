-- VerityForge initial schema (v1). Requires PostgreSQL with pgvector.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), email TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE workspaces (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL REFERENCES users(id), name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE projects (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id), name TEXT NOT NULL);
CREATE TABLE repositories (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id), local_path TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'standard' CHECK (scope IN ('standard','confidential')),
  excludes TEXT[] NOT NULL DEFAULT '{}');

CREATE TABLE coding_tasks (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  repository_id UUID NOT NULL REFERENCES repositories(id), user_id UUID NOT NULL REFERENCES users(id),
  objective TEXT NOT NULL, acceptance_criteria JSONB NOT NULL DEFAULT '[]', relevant_files TEXT[] NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','planning','executing','awaiting_approval',
    'testing','completed','failed','cancelled')),
  token_budget INT, estimated_cost NUMERIC(12,6), outcome TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX ON coding_tasks (user_id, state);
CREATE TABLE task_steps (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES coding_tasks(id) ON DELETE CASCADE, ordinal INT NOT NULL,
  depends_on INT[] NOT NULL DEFAULT '{}', action TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE file_snapshots (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  repository_id UUID NOT NULL REFERENCES repositories(id), path TEXT NOT NULL, sha TEXT NOT NULL,
  summary TEXT, UNIQUE (repository_id, path, sha));  -- hashes and summaries only, never full contents
CREATE TABLE code_patches (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES coding_tasks(id) ON DELETE CASCADE, path TEXT NOT NULL, base_sha TEXT NOT NULL,
  diff TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','applied','rejected')));
CREATE TABLE test_runs (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES coding_tasks(id) ON DELETE CASCADE, command TEXT NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('passed','failed','not_executed','inferred_unverified')),
  output TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE verification_sessions (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id), answer TEXT NOT NULL, research_provider TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE factual_claims (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES verification_sessions(id) ON DELETE CASCADE, text TEXT NOT NULL,
  normalized TEXT NOT NULL, category TEXT NOT NULL, freshness_class TEXT NOT NULL,
  entities TEXT[], dates TEXT[], priority INT, span_start INT, span_end INT);
CREATE TABLE evidence_sources (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id UUID NOT NULL REFERENCES factual_claims(id) ON DELETE CASCADE, url TEXT NOT NULL, title TEXT,
  published_date TEXT, reliability REAL, stance TEXT CHECK (stance IN ('supports','contradicts','neutral')));
CREATE TABLE verification_results (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id UUID NOT NULL REFERENCES factual_claims(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('Verified Current','Potentially Stale','Contradicted',
    'Insufficient Evidence','Not Time-Sensitive','Verification Failed')),
  score INT CHECK (score BETWEEN 0 AND 100), score_breakdown JSONB, explanation TEXT, correction TEXT);

CREATE TABLE model_requests (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), task_id UUID, user_id UUID,
  provider TEXT NOT NULL, model TEXT NOT NULL, scope TEXT NOT NULL, latency_ms INT, attempts INT,
  status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());  -- no prompt content stored
CREATE TABLE token_usage (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES model_requests(id) ON DELETE CASCADE,
  input_tokens INT NOT NULL, output_tokens INT NOT NULL, cached_input_tokens INT NOT NULL DEFAULT 0,
  estimated_cost NUMERIC(12,6), actual_cost NUMERIC(12,6), source TEXT NOT NULL CHECK (source IN ('provider','approximate')));
CREATE TABLE budget_policies (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL REFERENCES users(id),
  per_request NUMERIC, per_task NUMERIC, daily NUMERIC, monthly NUMERIC, warn_ratio REAL DEFAULT 0.8);
CREATE TABLE approval_requests (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID REFERENCES coding_tasks(id), action TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL,
  impact TEXT, reason TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  decided_at TIMESTAMPTZ);
CREATE TABLE audit_events (id BIGSERIAL PRIMARY KEY, user_id UUID, event TEXT NOT NULL, detail JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX ON audit_events (created_at);  -- retention: purge rows older than configured window
CREATE TABLE provider_health (provider TEXT PRIMARY KEY, failures INT NOT NULL DEFAULT 0, open_until TIMESTAMPTZ);
CREATE TABLE extension_registry (id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
  contract_version TEXT NOT NULL, permissions TEXT[] NOT NULL DEFAULT '{}', enabled BOOLEAN NOT NULL DEFAULT false);
