"""Persistence for telemetry and audit events, so dashboard data survives an API restart.

Two backends behind one interface:
  - MemoryStore (default): the current in-memory behaviour; nothing persisted.
  - SqlStore: writes to SQLite (file path) or PostgreSQL (DATABASE_URL starting postgres://).
    The two share ANSI SQL with a placeholder shim (? vs %s). On Postgres the pgvector schema in
    database/migrations applies; here we create just the two tables we read back, idempotently.

Selected by DATABASE_URL:
  unset / empty           -> MemoryStore
  sqlite:///path or *.db  -> SqlStore(sqlite)
  postgres(ql)://...      -> SqlStore(postgres)  (requires psycopg)
"""
from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod


class Store(ABC):
    @abstractmethod
    def record_request(self, rec: dict) -> None: ...
    @abstractmethod
    def record_audit(self, ev: dict) -> None: ...
    @abstractmethod
    def requests(self, limit: int = 1000) -> list[dict]: ...
    @abstractmethod
    def audit(self, limit: int = 200) -> list[dict]: ...
    def close(self) -> None: ...


class MemoryStore(Store):
    """No persistence. The gateway/audit already keep their own in-memory lists; this is a no-op sink
    used when no DATABASE_URL is configured, so callers can treat storage uniformly."""

    def record_request(self, rec: dict) -> None:
        pass

    def record_audit(self, ev: dict) -> None:
        pass

    def requests(self, limit: int = 1000) -> list[dict]:
        return []

    def audit(self, limit: int = 200) -> list[dict]:
        return []


class SqlStore(Store):
    def __init__(self, url: str):
        self._lock = threading.Lock()
        if url.startswith("sqlite:///") or url.endswith(".db") or url == "sqlite://:memory:":
            import sqlite3
            path = ":memory:" if ":memory:" in url else url.replace("sqlite:///", "")
            self.kind = "sqlite"
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._ph = "?"
        else:
            import psycopg
            self.kind = "postgres"
            self._conn = psycopg.connect(url, autocommit=True)
            self._ph = "%s"
        self._init_schema()

    def _exec(self, sql: str, params: tuple = ()) -> None:
        sql = sql.replace("?", self._ph)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            if self.kind == "sqlite":
                self._conn.commit()

    def _query(self, sql: str, params: tuple = ()) -> list[tuple]:
        sql = sql.replace("?", self._ph)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()

    def _init_schema(self) -> None:
        # Minimal tables we read back; a superset of the columns in database/migrations/0001_init.sql.
        self._exec("""CREATE TABLE IF NOT EXISTS vf_model_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts DOUBLE PRECISION, task TEXT, model TEXT, provider TEXT,
            input_tokens INTEGER, output_tokens INTEGER, estimated_cost DOUBLE PRECISION,
            latency DOUBLE PRECISION, attempts INTEGER, scope TEXT)"""
                   if self.kind == "sqlite" else
                   """CREATE TABLE IF NOT EXISTS vf_model_requests (
            id BIGSERIAL PRIMARY KEY, ts DOUBLE PRECISION, task TEXT, model TEXT, provider TEXT,
            input_tokens INTEGER, output_tokens INTEGER, estimated_cost DOUBLE PRECISION,
            latency DOUBLE PRECISION, attempts INTEGER, scope TEXT)""")
        self._exec("""CREATE TABLE IF NOT EXISTS vf_audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts DOUBLE PRECISION, event TEXT, severity TEXT, detail TEXT)"""
                   if self.kind == "sqlite" else
                   """CREATE TABLE IF NOT EXISTS vf_audit_events (
            id BIGSERIAL PRIMARY KEY, ts DOUBLE PRECISION, event TEXT, severity TEXT, detail TEXT)""")

    def record_request(self, rec: dict) -> None:
        self._exec(
            "INSERT INTO vf_model_requests (ts, task, model, provider, input_tokens, output_tokens, "
            "estimated_cost, latency, attempts, scope) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (time.time(), rec.get("task"), rec["model"], rec["provider"], rec["in"], rec["out"],
             rec["cost"], rec["latency"], rec["attempts"], rec["scope"]))

    def record_audit(self, ev: dict) -> None:
        detail = json.dumps({k: v for k, v in ev.items() if k not in ("ts", "event", "severity")})
        self._exec("INSERT INTO vf_audit_events (ts, event, severity, detail) VALUES (?,?,?,?)",
                   (ev.get("ts", time.time()), ev["event"], ev.get("severity", "info"), detail))

    def requests(self, limit: int = 1000) -> list[dict]:
        rows = self._query(
            "SELECT task, model, provider, input_tokens, output_tokens, estimated_cost, latency, attempts, scope "
            "FROM vf_model_requests ORDER BY id DESC LIMIT ?", (limit,))
        keys = ("task", "model", "provider", "in", "out", "cost", "latency", "attempts", "scope")
        return [dict(zip(keys, r)) for r in reversed(rows)]

    def audit(self, limit: int = 200) -> list[dict]:
        rows = self._query("SELECT ts, event, severity, detail FROM vf_audit_events ORDER BY id DESC LIMIT ?",
                           (limit,))
        out = []
        for ts, event, severity, detail in rows:
            d = json.loads(detail) if detail else {}
            out.append({"ts": ts, "event": event, "severity": severity, **d})
        return out

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def make_store(url: str | None) -> Store:
    if not url:
        return MemoryStore()
    return SqlStore(url)
