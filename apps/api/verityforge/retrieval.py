"""Retrieval for RAG: chunking, BM25, n-gram vectors, Reciprocal Rank Fusion, passage selection.

Honesty note: the default vectorizer (HashedNgramEmbedder) captures lexical/morphological similarity via
hashed character n-grams. It is NOT a neural semantic embedder and will not bridge true synonyms.
A neural embedder can be plugged in via the Embedder protocol (see BifrostEmbedder, untested live)."""
from __future__ import annotations

import ast
import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from .security import PolicyViolation, SecurityContext

_STOP = {"the", "and", "for", "that", "this", "with", "from", "into", "are", "was", "has", "have", "add", "make",
         "its", "not", "can", "you", "all", "any", "use", "new", "get", "set", "self", "return", "def", "class",
         "import", "none", "true", "false", "should", "would", "could", "also", "when", "then", "than", "will"}
_SUFFIXES = ("ations", "ation", "ating", "ated", "ates", "ate", "ions", "ion", "ings", "ing", "ed", "es", "e", "s")


def stem(w: str) -> str:
    for s in _SUFFIXES:
        if len(w) - len(s) >= 4 and w.endswith(s):
            return w[: -len(s)]
    return w


def tokenize(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)  # camelCase -> camel Case
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", text)
    return [stem(w.lower()) for w in words if len(w) > 2 and w.lower() not in _STOP]


@dataclass
class Chunk:
    path: str
    start: int  # 1-based inclusive
    end: int
    text: str
    tokens: list[str] = field(default_factory=list)
    vec: list[float] | None = None


def chunk_file(path: str, text: str, window: int = 30) -> list[Chunk]:
    lines = text.splitlines()
    spans: list[tuple[int, int]] = []
    if path.endswith(".py"):
        try:
            for n in ast.walk(ast.parse(text)):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.end_lineno:
                    spans.append((n.lineno, min(n.end_lineno, n.lineno + 60)))
        except SyntaxError:
            pass
    if not spans:
        spans = [(i + 1, min(i + window, len(lines))) for i in range(0, len(lines), window)]
    out = []
    for s, e in spans:
        body = "\n".join(lines[s - 1: e])
        out.append(Chunk(path, s, e, body, tokenize(path + " " + body)))
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b, self.docs = k1, b, docs
        self.tf = [Counter(d) for d in docs]
        self.avg = (sum(len(d) for d in docs) / len(docs)) if docs else 0.0
        df: Counter = Counter()
        for d in self.tf:
            df.update(d.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        q = set(query)
        out = []
        for tf, doc in zip(self.tf, self.docs):
            s, ln = 0.0, len(doc)
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / (self.avg or 1)))
            out.append(s)
        return out


class Embedder(Protocol):
    remote: bool

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashedNgramEmbedder:
    """Local, deterministic, dependency-free: hashed word + char-trigram features, L2-normalised."""
    remote = False

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _feats(self, text: str) -> list[str]:
        toks = tokenize(text)
        f = list(toks) + [a + "_" + b for a, b in zip(toks, toks[1:])]
        for t in toks:
            p = f"^{t}$"
            f += [p[i:i + 3] for i in range(len(p) - 2)]
        return f

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for feat, c in Counter(self._feats(t)).items():
                h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
                v[h % self.dim] += (1 if (h >> 63) & 1 else -1) * (1 + math.log(c))
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class BifrostEmbedder:
    """Neural embeddings via Bifrost's OpenAI-compatible /v1/embeddings. Remote: never used for confidential
    repos. NOT verified against a live gateway."""
    remote = True

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 30.0):
        self.base, self.model, self.key, self.timeout = base_url.rstrip("/"), model, api_key, timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        h = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        r = httpx.post(f"{self.base}/v1/embeddings", json={"model": self.model, "input": texts},
                       headers=h, timeout=self.timeout)
        r.raise_for_status()
        return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]


def cosine(a: list[float], b: list[float]) -> float:
    d = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return d / (na * nb) if na and nb else 0.0


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion over ranked lists of item ids."""
    s: dict[int, float] = {}
    for r in rankings:
        for pos, i in enumerate(r):
            s[i] = s.get(i, 0.0) + 1.0 / (k + pos + 1)
    return s


def hybrid_rank(chunks: list[Chunk], query: str, extra_terms: list[str] = (), embedder: Embedder | None = None,
                ctx: SecurityContext | None = None, use_dense: bool = True) -> list[tuple[Chunk, float]]:
    """BM25 (+ expanded-query BM25) + dense similarity, fused by RRF. Returns chunks best-first."""
    if not chunks:
        return []
    q = tokenize(query)
    bm = BM25([c.tokens for c in chunks])
    s1 = bm.scores(q)
    lists = [[i for i in sorted(range(len(chunks)), key=lambda i: -s1[i]) if s1[i] > 0]]
    if extra_terms:
        s2 = bm.scores(q + tokenize(" ".join(extra_terms)))
        lists.append([i for i in sorted(range(len(chunks)), key=lambda i: -s2[i]) if s2[i] > 0])
    if use_dense:
        emb = embedder or HashedNgramEmbedder()
        if getattr(emb, "remote", False) and ctx is not None and ctx.confidential:
            raise PolicyViolation("Remote embedder may not process confidential repository content.")
        need = [c for c in chunks if c.vec is None]
        for c, v in zip(need, emb.embed([c.text for c in need])):
            c.vec = v
        qv = emb.embed([query + " " + " ".join(extra_terms)])[0]
        sim = [cosine(qv, c.vec) for c in chunks]
        lists.append([i for i in sorted(range(len(chunks)), key=lambda i: -sim[i]) if sim[i] > 0.05])
    fused = rrf(lists)
    return [(chunks[i], s) for i, s in sorted(fused.items(), key=lambda kv: -kv[1])]


def best_passages(query: str, text: str, k: int = 3, size: int = 400, must_include: list[str] = ()) -> list[str]:
    """Passage-level retrieval over a long document (e.g. a web page): keep only the best-matching windows.

    must_include: literal substrings (e.g. a version "3.12") that tokenization would drop. Windows containing
    them are strongly boosted, so the row/sentence about the claim's specific subject is not lost."""
    words = text.split()
    if len(words) <= size:
        return [text]
    step = size // 2
    wins = [" ".join(words[i:i + size]) for i in range(0, len(words), step)]
    bm = BM25([tokenize(w) for w in wins])
    sc = bm.scores(tokenize(query))
    terms = [t for t in must_include if t]
    if terms:
        boost = (max(sc) or 1.0) + 1.0  # outranks any pure BM25 window
        for i, w in enumerate(wins):
            sc[i] += boost * sum(t in w for t in terms)
    top = sorted(range(len(wins)), key=lambda i: -sc[i])[:k]
    return [wins[i] for i in sorted(top)]  # document order
