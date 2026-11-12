"""Stale-answer detection: claim extraction, freshness policy, evidence comparison, scoring."""
from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .judge import GUIDANCE as JUDGE_GUIDANCE
from .research import ResearchProvider, ResearchUnavailable, Source

STATUSES = ("Verified Current", "Potentially Stale", "Contradicted", "Insufficient Evidence",
            "Not Time-Sensitive", "Verification Failed")

# category -> (freshness class, max age in days before verification is demanded)
FRESHNESS_POLICY = {
    "software_api": ("rapid", 90),
    "lifecycle": ("rapid", 90),
    "pricing": ("rapid", 30),
    "availability": ("rapid", 30),
    "law_regulation": ("time_sensitive", 365),
    "leadership": ("time_sensitive", 365),
    "announcement": ("time_sensitive", 180),
    "statistics": ("time_sensitive", 730),
    "general": ("stable", 36500),
}

DEFAULT_WEIGHTS = {"evidence_quality": 0.25, "source_reliability": 0.25, "recency": 0.15,
                   "agreement": 0.25, "completeness": 0.10}

_OPINION = re.compile(r"(?i)\b(i think|i believe|you should|we recommend|i recommend|might|could|would|should|"
                      r"perhaps|maybe|in my opinion|better to|consider|if you)\b")
_CATEGORY_RULES = [
    ("pricing", re.compile(r"(?i)\$\s?\d|\b(price|pricing|costs?|per (month|year|user)|plan)\b")),
    ("lifecycle", re.compile(r"(?i)\b(supported|support(s|ed)?|end[- ]?of[- ]?life|eol|maintained|"
                             r"security updates|lts\b|still (get|receive|supported))\b")),
    ("software_api", re.compile(r"(?i)\b(api|sdk|version|v\d+(\.\d+)*|release[sd]?|library|framework)\b")),
    ("availability", re.compile(r"(?i)\b(available|availability|generally available|ga\b|region|discontinued|deprecated)\b")),
    ("law_regulation", re.compile(r"(?i)\b(law|regulation|act\b|gdpr|compliance|legal|statute)\b")),
    ("leadership", re.compile(r"(?i)\b(ceo|cto|cfo|founder|chairman|president|leads?)\b")),
    ("announcement", re.compile(r"(?i)\b(announced|launched|unveiled|released)\b")),
    ("statistics", re.compile(r"(?i)\b\d+(\.\d+)?\s?%|\b(percent|survey|study|users|market share)\b")),
]
_VERSION = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b")
_PRICE = re.compile(r"\$\s?(\d+(?:\.\d+)?)")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_DATE = re.compile(r"\b(20\d{2}|19\d{2})\b")
_ENTITY = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\.js)?(?:\s[A-Z0-9][A-Za-z0-9]*)*)\b")
_IMPERATIVE = {"use", "run", "install", "click", "open", "add", "create", "make", "try", "see", "note", "ensure",
               "set", "go", "check", "remember", "avoid", "keep", "read", "write", "call", "import", "configure"}

MAX_DISTINCT_VALUES = 3
PRIMARY_HINTS = ("docs.", "developer.", ".gov", "official", "pricing", "api.", "github.com", "europa.eu")


@dataclass
class Claim:
    id: str
    text: str
    normalized: str
    category: str
    freshness_class: str
    entities: list[str]
    dates: list[str]
    values: dict[str, list[str]]
    priority: int
    start: int
    end: int
    requires_verification: bool


@dataclass
class ClaimResult:
    claim: Claim
    status: str
    score: int
    explanation: str
    score_breakdown: dict[str, float] = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    supporting: list[str] = field(default_factory=list)
    contradicting: list[str] = field(default_factory=list)
    conflicting_sources: bool = False
    correction: str | None = None
    query: str | None = None


# "supports API version 2.4" / "supports v2" = a capability claim about a version, not a support-lifecycle claim
_SUPPORTS_VERSION = re.compile(r"(?i)\bsupports?\s+(api\s+|sdk\s+)?(version\s+|release\s+)?v?\d")


def categorize(text: str) -> str:
    for cat, pat in _CATEGORY_RULES:
        if cat == "lifecycle" and _SUPPORTS_VERSION.search(text):
            continue  # "X supports version N" is a capability claim, not a support-lifecycle claim
        if pat.search(text):
            return cat
    return "general"


def extract_claims(answer: str, policy: dict | None = None) -> list[Claim]:
    policy = policy or FRESHNESS_POLICY
    claims: list[Claim] = []
    # A period followed by a non-space (3.9, Node.js, v2.4) is part of a token, not a sentence end.
    for m in re.finditer(r"(?:[^.!?\n]|\.(?=\S))+[.!?]?", answer):
        sentence = m.group(0)
        if not sentence.strip():
            continue
        # split compound sentences on ", and" / "; " to isolate independent claims
        offset = m.start()
        prev_ents: list[str] = []
        for part in re.finditer(r"[^;]+?(?:,\s+and\s+|;|$)", sentence):
            seg = part.group(0)
            seg_clean = re.sub(r",\s+and\s+$|;$", "", seg).strip(" ,.")
            if len(seg_clean.split()) < 4 or _OPINION.search(seg_clean) or seg_clean.endswith("?"):
                continue
            cat = categorize(seg_clean)
            if cat == "general" and (len(seg_clean.split()) < 5 or seg_clean.split()[0].lower() in _IMPERATIVE):
                continue  # too short to be a checkable statement, or an instruction rather than a claim
            fclass, _ = policy.get(cat, ("stable", 36500))
            # strip leading API/SDK and trailing version tokens: the queried value must not bias the search
            ents = sorted({re.sub(r"\s+v?\d[\w.]*$", "", re.sub(r"^(API|SDK)\s+", "", e))
                           for e in _ENTITY.findall(seg_clean)} - {"API", "SDK", ""})[:6]
            ents = [e for e in ents if not any(e != o and re.search(rf"\b{re.escape(e)}\b", o) for o in ents)]
            if not ents and prev_ents:  # pronoun/ellipsis: inherit subject from the preceding clause
                ents = prev_ents
            prev_ents = ents or prev_ents
            start = offset + part.start() + (len(seg) - len(seg.lstrip()))
            c = Claim(
                id=f"clm-{len(claims) + 1}", text=seg_clean,
                normalized=re.sub(r"\s+", " ", seg_clean.lower()), category=cat, freshness_class=fclass,
                entities=ents, dates=_DATE.findall(seg_clean),
                values={"version": _VERSION.findall(seg_clean), "price": _PRICE.findall(seg_clean),
                        "percent": _PERCENT.findall(seg_clean)},
                priority={"rapid": 3, "time_sensitive": 2, "stable": 1}[fclass],
                start=start, end=start + len(seg_clean),
                requires_verification=fclass != "stable",
            )
            claims.append(c)
    return claims


def dedupe_claims(claims: list[Claim]) -> list[Claim]:
    seen, out = set(), []
    for c in claims:
        if c.normalized not in seen:
            seen.add(c.normalized)
            out.append(c)
    return out


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def mark_official(sources: list[Source], entities: list[str]) -> list[Source]:
    """A source is 'official' when its registrable domain label equals a claim entity (python.org for Python).
    Only the second-level label counts, so python.evil.com or mostlypython.com do not qualify.
    Heuristic: it ignores multi-part TLDs such as .co.uk."""
    wanted = {_alnum(e) for e in entities if _alnum(e)}
    for s in sources:
        parts = s.domain.split(":")[0].split(".")
        s.official = len(parts) >= 2 and _alnum(parts[-2]) in wanted
    return sources


def source_reliability(src: Source) -> float:
    if src.official:
        return 0.95
    d = src.domain + src.url.lower()
    if any(h in d for h in PRIMARY_HINTS):
        return 0.95
    if any(h in d for h in ("wikipedia.org", "reuters.com", "stackoverflow.com")):
        return 0.6
    return 0.4


def parse_date(s: str) -> datetime | None:
    """Accept ISO 8601 and RFC 2822 (the format Tavily returns). Unparseable -> None, never guessed."""
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def recency_score(date_str: str | None, max_age_days: int, now: datetime | None = None) -> float:
    if not date_str:
        return 0.3  # unknown recency: neutral-low, never treated as fresh
    now = now or datetime.now(timezone.utc)
    d = parse_date(date_str)
    if d is None:
        return 0.3
    age = (now - d).days
    return 1.0 if age <= max_age_days else max(0.0, 1 - (age - max_age_days) / max(max_age_days, 1))


def _kind(c: Claim) -> str:
    return next((k for k in ("version", "price", "percent") if c.values[k]), "version")


_QUERY_HINT = {"software_api": "current version official documentation",
               "lifecycle": "end of life support status official schedule", "pricing": "official pricing page",
               "availability": "availability status", "law_regulation": "current official text",
               "leadership": "current leadership announcement", "announcement": "official announcement",
               "statistics": "latest data source"}


def _subject_version(c: Claim) -> tuple[str, str] | None:
    """For "<Product> <version> ..." claims, return (product, version), e.g. ("Node.js", "18")."""
    for e in c.entities:
        m = re.search(rf"{re.escape(e)}\s+v?(\d+(?:\.\d+)*)\b", c.text)
        if m:
            return e, m.group(1)
    return None


def build_query(c: Claim) -> str:
    """Search with the claim's own wording minus the asserted values (so the query cannot bias results toward
    confirming them), plus a category hint that steers toward authoritative pages.

    Exception, lifecycle claims: in "Node.js 18 is still supported" the version is the SUBJECT being asked
    about, not an asserted value. Stripping it searched for "Node.js" in general, and pages about version 18
    only turned up by luck. So lifecycle queries name the exact version."""
    if c.category == "lifecycle":
        sv = _subject_version(c)
        if sv:
            return f"{sv[0]} {sv[1]} end of life date support status"
    text = _PRICE.sub("", _PERCENT.sub("", _VERSION.sub("", c.text)))
    for e in c.entities:  # bare major versions attached to a name ("Node.js 18")
        text = re.sub(rf"({re.escape(e)})\s+v?\d+(?:\.\d+)*\b", r"\1", text)
    missing = [e for e in c.entities if e.lower() not in text.lower()]  # subject inherited from a prior clause
    text = " ".join(missing + [text])
    text = re.sub(r"\b(per (month|year|user)|costs?)\b", " ", text, flags=re.I) if c.category == "pricing" else text
    text = re.sub(r"\s+", " ", text).strip(" ,.")
    hint = _QUERY_HINT.get(c.category, "facts")
    return f"{text} {hint}".strip()


def _values_in(text: str, kind: str) -> list[str]:
    return {"version": _VERSION, "price": _PRICE, "percent": _PERCENT}[kind].findall(text)


def compare(claim: Claim, sources: list[Source]) -> tuple[list[str], list[str], dict[str, set[str]]]:
    """Return (supporting urls, contradicting urls, observed values per source-url set)."""
    supp, contra = [], []
    for src in sources:
        for kind in ("version", "price", "percent"):
            claimed = claim.values[kind]
            if not claimed:
                continue
            found = _values_in(src.title + " " + src.content, kind)
            if not found or len(set(found)) > MAX_DISTINCT_VALUES:
                continue  # index/changelog pages enumerate many values; they cannot state the current one
            if set(claimed) & set(found):
                supp.append(src.url)
            else:
                contra.append(src.url)
    return sorted(set(supp)), sorted(set(contra)), {}


def score_claim(quality: float, reliability: float, recency: float, agreement: float, completeness: float,
                weights: dict | None = None) -> tuple[int, dict]:
    w = weights or DEFAULT_WEIGHTS
    parts = {"evidence_quality": quality, "source_reliability": reliability, "recency": recency,
             "agreement": agreement, "completeness": completeness}
    total = sum(w[k] * v for k, v in parts.items()) / sum(w.values())
    return round(100 * total), {k: round(v, 3) for k, v in parts.items()}


class VerificationEngine:
    def __init__(self, research: ResearchProvider | None, weights: dict | None = None,
                 policy: dict | None = None, max_claims: int = 10, judge=None):
        self.research, self.weights, self.judge = research, weights, judge
        self.policy, self.max_claims = policy or FRESHNESS_POLICY, max_claims

    def verify(self, answer: str) -> dict:
        claims = dedupe_claims(extract_claims(answer, self.policy))
        results = [self._verify_claim(c) for c in claims[: self.max_claims]]
        counts: dict[str, int] = {}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return {"answer": answer, "claims": results, "summary": counts,
                "note": "Scores are system confidence/freshness indicators, not probabilities."}

    def _verify_claim(self, c: Claim) -> ClaimResult:
        if not c.requires_verification:
            return ClaimResult(c, "Not Time-Sensitive", 0,
                               "Category policy classifies this claim as stable; no live check performed.")
        if self.research is None:
            return ClaimResult(c, "Verification Failed", 0, "No research provider configured; claim not verified.")
        q = build_query(c)
        try:
            sources = self.research.search(q)
        except ResearchUnavailable as e:
            return ClaimResult(c, "Verification Failed", 0, f"Live research unavailable: {e}. Not treated as false.", query=q)
        if not sources:
            return ClaimResult(c, "Insufficient Evidence", 10, "No sources returned; claim is unverified, not false.", query=q)
        max_age = self.policy[c.category][1]
        sources = sorted(mark_official(sources, c.entities), key=lambda s: -source_reliability(s))
        src_info = [{"url": s.url, "title": s.title, "published_date": s.published_date,
                     "reliability": source_reliability(s)} for s in sources]
        if self.judge is not None:
            # Judge first: live runs showed numeric matching treats any page that mentions another version as
            # "contradicting". The judge must cite a retrieved URL and quote it verbatim, so it cannot invent evidence.
            judged = self._judged(c, sources, src_info, max_age, q)
            if judged is not None:
                return judged
        supp, contra, _ = compare(c, sources)  # deterministic fallback (offline/mock, or judge unclear/unavailable)
        pool = supp + contra
        if not pool:
            sc, bd = score_claim(0.2, max(source_reliability(s) for s in sources), 0.3, 0.0, 0.2, self.weights)
            return ClaimResult(c, "Insufficient Evidence", min(sc, 40),
                               "Sources found, but none state a comparable value; cannot confirm or refute.",
                               bd, src_info, query=q)
        rel = {s.url: s for s in sources}
        best = max(pool, key=lambda u: source_reliability(rel[u]))
        reliab = source_reliability(rel[best])
        rec = recency_score(rel[best].published_date, max_age)
        conflict = bool(supp) and bool(contra)
        if conflict:
            agreement = len(supp) / len(pool)
            status, expl = "Contradicted" if agreement < 0.5 else "Verified Current", ""
            expl = (f"Sources conflict: {len(supp)} support and {len(contra)} contradict the claim. "
                    "Both sides are listed; no winner is assumed.")
            status = "Insufficient Evidence" if 0.4 <= agreement <= 0.6 else status
        elif supp:
            agreement, status = 1.0, "Verified Current"
            expl = f"{len(supp)} source(s) state the claimed value."
            if rec < 0.5 and rel[best].published_date:
                status, expl = "Potentially Stale", expl + " Best source is old relative to the freshness window."
        else:
            agreement, status = 0.0, "Contradicted"
            observed = sorted({v for u in contra for v in _values_in(rel[u].content, _kind(c))})[:3]
            expl = (f"Sources report different value(s) {observed} than the claim." if observed
                    else "Sources state a different value than the claim.")
            if rec < 0.5:
                status = "Potentially Stale"
        sc, bd = score_claim(0.9 if (supp or contra) else 0.3, reliab, rec, agreement, 1.0, self.weights)
        correction = None
        if status in ("Contradicted", "Potentially Stale") and contra and not conflict:
            observed = _values_in(rel[best].content, _kind(c))
            if observed:
                correction = f"Current sources ({best}) list {observed[0]}."
        return ClaimResult(c, status, sc, expl, bd, src_info, supp, contra, conflict, correction, q)

    def _judged(self, c: Claim, sources: list[Source], src_info: list[dict], max_age: int, q: str):
        """LLM comparison fallback. Evidence quality is scored lower than deterministic matching."""
        two_step = c.category == "lifecycle" and hasattr(self.judge, "extract_eol")
        v = self.judge.extract_eol(c.text, sources) if two_step else \
            self.judge(c.text, sources, JUDGE_GUIDANCE.get(c.category, ""))
        if v is None:
            return None
        src, quote = v["source"], v["quote"]
        supports = v["stance"] == "supports"
        if v.get("two_step"):
            # Supported/not is decided in code from the extracted EOL date; source recency is irrelevant.
            status = "Verified Current" if supports else "Contradicted"
            eol = v["eol_date"]
            if eol == "ended":  # source states the version is end-of-life without giving a date
                expl = (f"Two-step lifecycle check ({v['model']}): the source states this version has reached "
                        f"end-of-life (no date given; confirmed in code from the verbatim quote).")
                correction = f'Reached end-of-life; source {src.url} states: "{quote}"'
            else:
                expl = (f"Two-step lifecycle check ({v['model']}): extracted end-of-life = {eol}, compared to "
                        f"{v['today']} in code. {'Still supported.' if supports else 'Past end-of-life.'}")
                correction = None if supports else f'Reached end-of-life {eol}; source {src.url} states: "{quote}"'
        else:
            rec = recency_score(src.published_date, max_age)
            status = "Verified Current" if supports else "Contradicted"
            if rec < 0.5 and src.published_date:
                status = "Potentially Stale"
            expl = (f"Judged by LLM ({v['model']}) because no comparable numeric value was found. "
                    f"The cited text was verified to appear in the source.")
            correction = None if supports else f'Source {src.url} states: "{quote}"'
        sc, bd = score_claim(0.6, source_reliability(src), 1.0 if v.get("two_step") else recency_score(src.published_date, max_age),
                             1.0 if supports else 0.0, 1.0, self.weights)
        return ClaimResult(c, status, sc, expl, bd, src_info,
                           [src.url] if supports else [], [] if supports else [src.url], False, correction, q)
