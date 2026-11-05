"""Repository intelligence and token-minimizing context building."""
from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .gateway import approx_tokens
from .retrieval import Chunk, Embedder, chunk_file, hybrid_rank

DEFAULT_EXCLUDES = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist", ".next",
                    ".pytest_cache", "coverage"}
CODE_EXT = {".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
            ".jsx": "javascript", ".go": "go", ".java": "java", ".rs": "rust"}
MAX_FILE_BYTES = 256_000
_JS_SYM = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|const|interface|type)\s+([A-Za-z_$][\w$]*)", re.M)
_JS_IMP = re.compile(r"""(?:import[^'"]*from\s*|require\()\s*['"]([^'"]+)['"]""")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


@dataclass
class FileInfo:
    path: str
    language: str
    sha: str
    size: int
    symbols: list[tuple[str, int]] = field(default_factory=list)  # (name, line)
    imports: list[str] = field(default_factory=list)
    summary: str = ""


def sha_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


class RepoIndex:
    def __init__(self, root: str, excludes: set[str] | None = None):
        self.root = Path(root).resolve()
        self.excludes = DEFAULT_EXCLUDES | (excludes or set())
        self.files: dict[str, FileInfo] = {}
        self.graph: dict[str, set[str]] = {}
        self.reverse: dict[str, set[str]] = {}
        self.scans = 0
        self._chunks: dict[str, tuple[str, list[Chunk]]] = {}  # path -> (sha, chunks); reused while unchanged

    def _discover(self) -> list[Path]:
        try:  # Git-aware discovery: respects .gitignore
            out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=self.root,
                                 capture_output=True, text=True, timeout=20, check=True).stdout.split("\n")
            paths = [self.root / p for p in out if p]
        except (subprocess.SubprocessError, OSError):
            paths = [p for p in self.root.rglob("*") if p.is_file()]
        return [p for p in paths if p.is_file() and not (set(p.relative_to(self.root).parts) & self.excludes)
                and p.suffix in CODE_EXT and p.stat().st_size <= MAX_FILE_BYTES]

    def build(self) -> None:
        """Incremental: unchanged files (same sha) keep their index entries."""
        self.scans += 1
        seen = set()
        for p in self._discover():
            rel = p.relative_to(self.root).as_posix()
            seen.add(rel)
            data = p.read_bytes()
            sha = sha_of(data)
            if rel in self.files and self.files[rel].sha == sha:
                continue
            self.files[rel] = self._parse(rel, p.suffix, data.decode("utf-8", "replace"), sha, len(data))
        for gone in set(self.files) - seen:
            del self.files[gone]
        self._graph()

    def _parse(self, rel: str, ext: str, text: str, sha: str, size: int) -> FileInfo:
        info = FileInfo(rel, CODE_EXT[ext], sha, size)
        if ext == ".py":
            try:
                for n in ast.walk(ast.parse(text)):
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        info.symbols.append((n.name, n.lineno))
                    elif isinstance(n, ast.Import):
                        info.imports += [a.name for a in n.names]
                    elif isinstance(n, ast.ImportFrom) and n.module:
                        info.imports.append(("." * n.level) + n.module)
            except SyntaxError:
                pass
        else:
            info.symbols = [(m.group(1), text[: m.start()].count("\n") + 1) for m in _JS_SYM.finditer(text)]
            info.imports = _JS_IMP.findall(text)
        info.summary = f"{rel}: {', '.join(n for n, _ in info.symbols[:12])}"
        return info

    def _resolve(self, src: str, imp: str) -> str | None:
        base = Path(src).parent
        cands = []
        if imp.startswith("."):
            dots = len(imp) - len(imp.lstrip("."))
            mod = imp.lstrip(".").replace(".", "/")
            d = base
            for _ in range(dots - 1):
                d = d.parent
            rel = (d / mod).as_posix() if mod else d.as_posix()
            if src.endswith(".py"):
                cands = [rel + ".py", rel + "/__init__.py"]
            else:
                cands = [rel + e for e in ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx")]
            cands = [Path(c).as_posix() for c in cands]
        else:
            mod = imp.replace(".", "/")
            cands = [mod + ".py", mod + "/__init__.py"]
            cands += [Path(src).parts[0] + "/" + mod + ".py"]
            cands += [f for f in self.files if f.endswith("/" + mod + ".py")]
        for c in cands:
            c = str(Path(c).as_posix()).lstrip("./") if c.startswith("./") else c
            if c in self.files and c != src:
                return c
        return None

    def _graph(self) -> None:
        self.graph = {f: set() for f in self.files}
        self.reverse = {f: set() for f in self.files}
        for f, info in self.files.items():
            for imp in info.imports:
                t = self._resolve(f, imp)
                if t:
                    self.graph[f].add(t)
                    self.reverse[t].add(f)

    def invalidate(self, rel: str) -> set[str]:
        """After an edit: drop the file's entry and report dependents whose context is stale."""
        self.files.pop(rel, None)
        return set(self.reverse.get(rel, set()))

    # ---- relevance + context ----
    def rank_lexical(self, task: str, limit: int = 6) -> list[tuple[str, float]]:
        words = {w.lower() for w in _WORD.findall(task)}
        scores: dict[str, float] = {}
        for f, info in self.files.items():
            hay = {w.lower() for w in _WORD.findall(f)} | {s.lower() for s, _ in info.symbols}
            hits = len(words & hay)
            if hits:
                scores[f] = float(hits)
        for f in list(scores):  # one-hop dependency neighbors get a smaller boost
            for n in self.graph.get(f, set()) | self.reverse.get(f, set()):
                scores[n] = max(scores.get(n, 0.0), scores[f] * 0.4)
        return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


    # ---- retrieval-augmented context (chunk-level hybrid search) ----
    def _all_chunks(self) -> list[Chunk]:
        out: list[Chunk] = []
        for rel, info in self.files.items():
            cached = self._chunks.get(rel)
            if not cached or cached[0] != info.sha:  # re-chunk only changed files
                text = (self.root / rel).read_text("utf-8", "replace")
                cached = (info.sha, chunk_file(rel, text))
                self._chunks[rel] = cached
            out.extend(cached[1])
        for gone in set(self._chunks) - set(self.files):
            del self._chunks[gone]
        return out

    def retrieve(self, task: str, extra_terms: list[str] = (), embedder: Embedder | None = None,
                 ctx=None, use_dense: bool = False) -> list[tuple[Chunk, float]]:
        # Dense vectors are opt-in: on the retrieval benchmark the n-gram vectors added no value over BM25.
        # Supplying a (neural) embedder enables them.
        return hybrid_rank(self._all_chunks(), task, list(extra_terms), embedder, ctx, use_dense or embedder is not None)

    def rank(self, task: str, limit: int = 6, **kw) -> list[tuple[str, float]]:
        """File ranking: best chunk score per file, plus a smaller boost for dependency neighbors."""
        scores: dict[str, float] = {}
        for ch, s in self.retrieve(task, **kw):
            scores[ch.path] = max(scores.get(ch.path, 0.0), s)
        for f in list(scores):
            for n in self.graph.get(f, set()) | self.reverse.get(f, set()):
                scores[n] = max(scores.get(n, 0.0), scores[f] * 0.4)
        return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]

    def build_context(self, task: str, token_budget: int = 2000, extra_terms: list[str] = (),
                      embedder: Embedder | None = None, ctx=None) -> dict:
        """Hierarchy: metadata -> relevant files -> best-matching chunks (exact code), within the token budget."""
        hits = self.retrieve(task, extra_terms, embedder, ctx)
        scores: dict[str, float] = {}
        for ch, s in hits:
            scores[ch.path] = max(scores.get(ch.path, 0.0), s)
        for f in list(scores):
            for n in self.graph.get(f, set()) | self.reverse.get(f, set()):
                scores[n] = max(scores.get(n, 0.0), scores[f] * 0.4)
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        parts = [f"repo files={len(self.files)} languages={sorted({i.language for i in self.files.values()})}"]
        used = approx_tokens(parts[0])
        for f, _ in ranked:
            used += approx_tokens(self.files[f].summary)
            parts.append(self.files[f].summary)
        top_files = {f for f, _ in ranked}
        included = []
        for ch, _ in hits[:12]:
            if ch.path not in top_files:
                continue
            body = "\n".join(ch.text.splitlines()[:40])
            cost = approx_tokens(body)
            if used + cost > token_budget:
                continue
            used += cost
            included.append((ch.path, ch.start))
            parts.append(f"--- {ch.path}:{ch.start}-{ch.end}\n{body}")
        full = sum(approx_tokens((self.root / f).read_text("utf-8", "replace")) for f in self.files)
        return {"text": "\n".join(parts), "tokens": used, "files": [f for f, _ in ranked],
                "excerpts": included, "full_repo_tokens": full}
