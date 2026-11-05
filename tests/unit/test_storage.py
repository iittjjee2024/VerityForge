from verityforge.storage import MemoryStore, SqlStore, make_store

REQ = {"task": "t1", "model": "groq/x", "provider": "bifrost", "in": 100, "out": 20,
       "cost": 0.0003, "latency": 1.2, "attempts": 1, "scope": "standard"}
EV = {"ts": 123.0, "event": "approval_rejected", "severity": "warning", "target": "a.py"}


def test_memory_store_is_noop():
    s = make_store(None)
    assert isinstance(s, MemoryStore)
    s.record_request(REQ)
    s.record_audit(EV)
    assert s.requests() == [] and s.audit() == []


def test_sqlite_round_trip(tmp_path):
    db = str(tmp_path / "vf.db")
    s = SqlStore(f"sqlite:///{db}")
    s.record_request(REQ)
    s.record_audit(EV)
    reqs = s.requests()
    assert len(reqs) == 1 and reqs[0]["model"] == "groq/x" and reqs[0]["in"] == 100
    aud = s.audit()
    assert aud[0]["event"] == "approval_rejected" and aud[0]["target"] == "a.py"
    s.close()


def test_sqlite_survives_reopen(tmp_path):
    db = str(tmp_path / "vf.db")
    s1 = SqlStore(f"sqlite:///{db}")
    s1.record_request(REQ)
    s1.record_audit(EV)
    s1.close()
    s2 = SqlStore(f"sqlite:///{db}")  # simulates an API restart against the same database
    assert len(s2.requests()) == 1 and len(s2.audit()) == 1
    s2.close()


def test_audit_detail_is_json_roundtripped(tmp_path):
    s = SqlStore("sqlite://:memory:")
    s.record_audit({"ts": 1.0, "event": "e", "severity": "info", "action": "write_file", "target": "x", "n": 3})
    row = s.audit()[0]
    assert row["action"] == "write_file" and row["n"] == 3
    s.close()
