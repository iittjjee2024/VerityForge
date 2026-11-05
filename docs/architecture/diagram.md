# Component diagram

```mermaid
flowchart TB
  subgraph Client
    UI[Next.js dashboard<br/>7 pages]
    CLI[CLI - not built]
  end
  UI -->|/api/v1/*| API

  subgraph Backend[FastAPI backend - modular monolith]
    API[API & routes<br/>main.py]
    SEC[Security & Policy<br/>scopes, approval gate, audit]
    GW[Model Gateway<br/>routing, failover, budget]
    AGENT[Coding Agent<br/>plan/patch/test/repair]
    VERIFY[Verification Engine<br/>claims, judge, scoring]
    RAG[Retrieval & Repo index<br/>BM25, context]
    SBX[Docker sandbox]
  end

  API --> SEC
  API --> AGENT
  API --> VERIFY
  AGENT --> RAG
  AGENT --> GW
  AGENT --> SBX
  AGENT --> SEC
  VERIFY --> GW
  VERIFY --> RESEARCH
  GW --> SEC

  GW -->|OpenAI-compatible| BIFROST[Bifrost gateway]
  BIFROST --> GROQ[Groq]
  BIFROST --> GEMINI[Gemini]
  BIFROST -.-> LOCAL[Local model<br/>confidential only]
  RESEARCH[Tavily adapter] --> TAVILY[Tavily API]

  subgraph State[State - in-memory today]
    PG[(PostgreSQL + pgvector<br/>schema ready, not wired)]
    REDIS[(Redis<br/>planned)]
  end
  API -.-> PG
```

Confidential repositories: the gateway refuses any remote provider for repo-derived content and falls closed to a
local model, enforced in `security.py` / `gateway.py`, not in prompts.
