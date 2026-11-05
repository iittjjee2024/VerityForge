"""Retrieval benchmark: file-level recall@3 / MRR for the old keyword ranking vs BM25 vs hybrid (BM25+n-gram vectors).

SYNTHETIC repo and queries, authored by the developer BEFORE the first run. Small (14 queries): treat as a
regression/sanity check, not evidence of real-world retrieval quality. Query expansion (LLM) and neural
embeddings are NOT measured here (they need a live model).
Usage: python benchmarks/retrieval/run.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))
from verityforge.repo import RepoIndex  # noqa: E402

MODULES = {
    "shop/catalog.py": '''def list_products(db):
    """Return every product in the catalog."""
    return db.all()

def find_product(db, product_id):
    """Look up one product by its identifier."""
    return db.get(product_id)
''',
    "shop/paging.py": '''def paginate(items, page, size):
    """Slice a sequence into one page of results using page number and size."""
    start = (page - 1) * size
    return items[start:start + size]
''',
    "billing/invoice.py": '''def compute_total(lines, tax_rate):
    """Sum line amounts and apply sales tax to produce the amount due."""
    return sum(lines) * (1 + tax_rate)

def render_invoice(total):
    return f"Amount due: {total}"
''',
    "auth/session.py": '''def login(user, password, store):
    """Verify credentials and open an authenticated session token."""
    return store.create(user)

def logout(token, store):
    """Invalidate a session so the token can no longer be used."""
    store.delete(token)
''',
    "auth/hashing.py": '''import hashlib

def hash_password(pw, salt):
    """Derive a salted digest of a password for safe storage."""
    return hashlib.sha256((salt + pw).encode()).hexdigest()
''',
    "search/index.py": '''def build_index(documents):
    """Create an inverted index mapping each word to the documents containing it."""
    idx = {}
    for i, d in enumerate(documents):
        for w in d.split():
            idx.setdefault(w, set()).add(i)
    return idx
''',
    "notify/mailer.py": '''def send_email(smtp, to, subject, body):
    """Deliver a message to a recipient through the SMTP server."""
    smtp.send(to, subject, body)
''',
    "infra/cache.py": '''class TTLCache:
    """Key value store whose entries expire after a time to live."""
    def __init__(self, ttl):
        self.ttl, self.data = ttl, {}

    def get(self, key, now):
        v = self.data.get(key)
        return v[1] if v and v[0] > now else None
''',
    "export/csv_writer.py": '''def write_csv(rows, handle):
    """Serialize records as comma separated lines into an open file."""
    for r in rows:
        handle.write(",".join(map(str, r)) + "\\n")
''',
    "infra/retry.py": '''import time

def with_retries(fn, attempts, delay):
    """Call a function again after failures, waiting between attempts, until it succeeds."""
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            time.sleep(delay * 2 ** i)
    raise RuntimeError("exhausted")
''',
    "geo/distance.py": '''import math

def haversine(lat1, lon1, lat2, lon2):
    """Great circle distance in kilometres between two coordinates on Earth."""
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))
''',
    "ops/healthcheck.py": '''def check_database(conn):
    """Report whether the database connection is alive and responding."""
    return conn.ping()
''',
}
# (query, gold file). Some intentionally use words absent from the target code (vocabulary mismatch).
QUERIES = [
    ("add a page size limit to the product listing", "shop/paging.py"),
    ("show only ten products per page", "shop/paging.py"),
    ("calculate how much the customer owes including tax", "billing/invoice.py"),
    ("users cannot sign in with correct credentials", "auth/session.py"),
    ("end the user's session when they sign out", "auth/session.py"),
    ("store passwords securely", "auth/hashing.py"),
    ("full text lookup of documents by word", "search/index.py"),
    ("email recipients are not receiving messages", "notify/mailer.py"),
    ("entries should expire automatically", "infra/cache.py"),
    ("export records to a spreadsheet file", "export/csv_writer.py"),
    ("transient failures should be attempted again with backoff", "infra/retry.py"),
    ("how far apart are two cities", "geo/distance.py"),
    ("is the database up", "ops/healthcheck.py"),
    ("fetch a single product by id", "shop/catalog.py"),
]


def metrics(ranker, idx):
    hits = rr = 0.0
    for q, gold in QUERIES:
        files = [f for f, _ in ranker(q)]
        if gold in files[:3]:
            hits += 1
        if gold in files[:10]:
            rr += 1 / (files.index(gold) + 1)
    n = len(QUERIES)
    return round(hits / n, 3), round(rr / n, 3)


def run() -> dict:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for p, src in MODULES.items():
            (root / p).parent.mkdir(parents=True, exist_ok=True)
            (root / p).write_text(src)
        idx = RepoIndex(str(root))
        idx.build()
        systems = {
            "keyword-overlap (old)": lambda q: idx.rank_lexical(q, 10),
            "BM25 chunks": lambda q: idx.rank(q, 10, use_dense=False),
            "hybrid BM25 + n-gram vectors (RRF)": lambda q: idx.rank(q, 10, use_dense=True),
        }
        return {name: dict(zip(("recall@3", "MRR@10"), metrics(fn, idx))) for name, fn in systems.items()}


if __name__ == "__main__":
    res = run()
    import json
    (Path(__file__).with_name("results.json")).write_text(
        json.dumps({"queries": len(QUERIES), "systems": res}, indent=2), "utf-8")
    print(f"{'system':<38} {'recall@3':>9} {'MRR@10':>8}   ({len(QUERIES)} queries, synthetic)")
    for k, v in res.items():
        print(f"{k:<38} {v['recall@3']:>9} {v['MRR@10']:>8}")
