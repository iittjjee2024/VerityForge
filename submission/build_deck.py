"""Builds submission/VerityForge.pptx. Run: python submission/build_deck.py
All figures are taken from measured results in benchmarks/, demo/transcripts/ and the test suites."""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

NAVY = RGBColor(0x06, 0x0B, 0x18)
PANEL = RGBColor(0x10, 0x1A, 0x33)
EDGE = RGBColor(0x1E, 0x3A, 0x5F)
CYAN = RGBColor(0x22, 0xD3, 0xEE)
VIOLET = RGBColor(0xA7, 0x8B, 0xFA)
GREEN = RGBColor(0x34, 0xD3, 0x99)
WHITE = RGBColor(0xE2, 0xE8, 0xF0)
MUTED = RGBColor(0x94, 0xA3, 0xB8)

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
W, H = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]


def bg(slide):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = NAVY
    # subtle accent bar
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Inches(0.08))
    bar.fill.solid(); bar.fill.fore_color.rgb = CYAN; bar.line.fill.background()


def text(slide, x, y, w, h, s, size=18, color=WHITE, bold=False, align=PP_ALIGN.LEFT, font="Segoe UI"):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    lines = s if isinstance(s, list) else [s]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), bold, color, font
    return tb


def title(slide, t, sub=None):
    text(slide, Inches(0.6), Inches(0.35), Inches(12), Inches(0.8), t, 32, WHITE, True)
    if sub:
        text(slide, Inches(0.6), Inches(1.05), Inches(12), Inches(0.5), sub, 16, CYAN)


def panel(slide, x, y, w, h, heading, body, accent=CYAN, body_size=14):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    box.adjustments[0] = 0.06
    box.fill.solid(); box.fill.fore_color.rgb = PANEL
    box.line.color.rgb = EDGE; box.line.width = Pt(1)
    text(slide, x + Inches(0.2), y + Inches(0.12), w - Inches(0.4), Inches(0.5), heading, 17, accent, True)
    text(slide, x + Inches(0.2), y + Inches(0.6), w - Inches(0.4), h - Inches(0.7),
         [f"•  {b}" for b in body], body_size, WHITE)


def stat(slide, x, y, w, big, label, color=CYAN):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, Inches(1.55))
    box.adjustments[0] = 0.08
    box.fill.solid(); box.fill.fore_color.rgb = PANEL
    box.line.color.rgb = EDGE
    text(slide, x, y + Inches(0.15), w, Inches(0.8), big, 34, color, True, PP_ALIGN.CENTER)
    text(slide, x + Inches(0.1), y + Inches(0.9), w - Inches(0.2), Inches(0.6), label, 12, MUTED, False,
         PP_ALIGN.CENTER)


def table(slide, x, y, w, rows, col_w, size=12):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), x, y, w, Inches(0.4) * len(rows))
    t = shape.table
    for ci, cw in enumerate(col_w):
        t.columns[ci].width = Emu(int(w * cw))
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            c = t.cell(ri, ci)
            c.fill.solid()
            c.fill.fore_color.rgb = EDGE if ri == 0 else PANEL
            tf = c.text_frame
            tf.paragraphs[0].text = ""
            r = tf.paragraphs[0].add_run()
            r.text = val
            r.font.size, r.font.name = Pt(size), "Segoe UI"
            r.font.bold = ri == 0
            r.font.color.rgb = CYAN if ri == 0 else WHITE


def footer(slide, n):
    text(slide, Inches(0.6), H - Inches(0.45), Inches(8), Inches(0.3),
         "VerityForge  ·  github.com/iittjjee2024/VerityForge", 10, MUTED)
    text(slide, W - Inches(1.2), H - Inches(0.45), Inches(0.6), Inches(0.3), str(n), 10, MUTED, align=PP_ALIGN.RIGHT)


# ---- 1. Title ---------------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s)
text(s, Inches(0.8), Inches(2.0), Inches(11.5), Inches(1.3), "VerityForge", 66, CYAN, True)
text(s, Inches(0.8), Inches(3.3), Inches(11.5), Inches(1.0),
     "A token-efficient coding agent and a real-time stale-answer detector — one platform", 26, WHITE)
text(s, Inches(0.8), Inches(4.4), Inches(11.5), Inches(0.6),
     "Built on Bifrost by Maxim AI  ·  Live evidence from Tavily", 18, VIOLET)
text(s, Inches(0.8), Inches(6.3), Inches(11.5), Inches(0.5),
     "Global AI Hackathon  ·  github.com/iittjjee2024/VerityForge", 14, MUTED)

# ---- 2. Problem -------------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "The problem", "Two failures that cost teams time, money and trust")
panel(s, Inches(0.6), Inches(1.8), Inches(5.9), Inches(4.6), "Coding agents waste tokens", [
    "Send whole files or whole repositories to the model",
    "Repeat repo-wide scans on every step",
    "Declare success because the model says so",
    "On rate-limited tiers, large prompts are rejected outright",
], CYAN, 16)
panel(s, Inches(6.8), Inches(1.8), Inches(5.9), Inches(4.6), "AI answers go stale", [
    "Versions, prices and support dates change constantly",
    "Models state outdated facts with full confidence",
    "Users can't tell which sentence to distrust",
    "No evidence, no dates, no correction",
], VIOLET, 16)
footer(s, 2)

# ---- 3. Solution ------------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "The solution", "One platform, shared gateway, budget, security and retrieval")
panel(s, Inches(0.6), Inches(1.8), Inches(5.9), Inches(4.6), "Coding agent", [
    "Builds a minimal context: only the code the task needs",
    "Plans and proposes exact patches, including new files",
    "Every diff waits for human approval",
    "Tests run in a network-less Docker sandbox",
    "Bounded repair, escalating to a larger model",
    "Done ONLY when tests pass and every part is done",
], CYAN, 15)
panel(s, Inches(6.8), Inches(1.8), Inches(5.9), Inches(4.6), "Stale-answer detector", [
    "Splits an answer into individual factual claims",
    "Classifies how fast each fact changes",
    "Searches Tavily only for time-sensitive claims",
    "Verdict + transparent score + cited sources + dates",
    "Suggests a correction; shows conflicts side by side",
    "Missing evidence = unverified, never 'false'",
], VIOLET, 15)
footer(s, 3)

# ---- 4. Architecture --------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "Architecture", "Modular monolith with clean service boundaries")


def node(x, y, w, h, label, color=CYAN):
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    b.fill.solid(); b.fill.fore_color.rgb = PANEL; b.line.color.rgb = color; b.line.width = Pt(1.5)
    text(s, x, y + Inches(0.12), w, h, label, 13, WHITE, True, PP_ALIGN.CENTER)


node(Inches(0.6), Inches(1.9), Inches(3.0), Inches(0.8), "Web dashboard (9 pages)")
node(Inches(0.6), Inches(2.9), Inches(3.0), Inches(0.8), "CLI  ·  REST API  ·  Plugins")
node(Inches(4.3), Inches(1.9), Inches(4.6), Inches(0.8), "FastAPI  ·  Auth  ·  Security & Policy", VIOLET)
node(Inches(4.3), Inches(2.9), Inches(2.2), Inches(0.8), "Coding Agent")
node(Inches(6.7), Inches(2.9), Inches(2.2), Inches(0.8), "Verification Engine")
node(Inches(4.3), Inches(3.9), Inches(2.2), Inches(0.8), "Retrieval / RAG")
node(Inches(6.7), Inches(3.9), Inches(2.2), Inches(0.8), "Model Gateway + Budget", VIOLET)
node(Inches(4.3), Inches(4.9), Inches(2.2), Inches(0.8), "Docker sandbox", GREEN)
node(Inches(6.7), Inches(4.9), Inches(2.2), Inches(0.8), "Audit + persistence", GREEN)
node(Inches(9.6), Inches(2.4), Inches(3.1), Inches(0.9), "Bifrost gateway", VIOLET)
node(Inches(9.6), Inches(3.5), Inches(1.5), Inches(0.8), "Groq")
node(Inches(11.2), Inches(3.5), Inches(1.5), Inches(0.8), "Gemini")
node(Inches(9.6), Inches(4.6), Inches(3.1), Inches(0.9), "Tavily web research", VIOLET)
text(s, Inches(0.6), Inches(6.1), Inches(12), Inches(0.6),
     "Business logic never names a provider: every model call goes through one provider-independent gateway.",
     14, MUTED)
footer(s, 4)

# ---- 5. Bifrost + Tavily ----------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s)
title(s, "Bifrost and Tavily, meaningfully integrated", "Both exercised live, not mocked")
panel(s, Inches(0.6), Inches(1.8), Inches(5.9), Inches(4.6), "Bifrost by Maxim AI — the LLM gateway", [
    "Every model call routes through Bifrost (OpenAI-compatible)",
    "Multi-provider: Groq for coding, Gemini for judging",
    "Tier routing: small model first, larger on repair",
    "Failover: dead model -> healthy fallback, no wasted retries",
    "Provider-reported token usage feeds budgets + analytics",
    "Keys referenced as env vars — never committed",
], VIOLET, 15)
panel(s, Inches(6.8), Inches(1.8), Inches(5.9), Inches(4.6), "Tavily — live evidence", [
    "Targeted query per time-sensitive claim",
    "Returns sources, content and publication dates",
    "Credit usage tracked per search (1 credit, basic depth)",
    "Official domains ranked first (python.org, nodejs.org)",
    "Outage / rate limit -> 'Verification Failed', never 'false'",
    "Fetched pages are treated as untrusted data",
], CYAN, 15)
footer(s, 5)

# ---- 6. How AI is used ------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "How AI is used", "Every AI step has a deterministic guardrail")
table(s, Inches(0.6), Inches(1.8), Inches(12.1), [
    ["Where", "AI technique", "Guardrail"],
    ["Coding agent", "LLM plans + writes patches (structured JSON)", "Approved, test-verified, completeness-checked"],
    ["Token reduction", "RAG: BM25 code chunks, RRF, import graph", "Hard token budget per call"],
    ["Model routing", "Small -> large escalation; Groq + Gemini via Bifrost", "Budget checked before every call"],
    ["Query expansion", "LLM suggests likely identifiers", "Sanitised to identifier tokens"],
    ["Evidence judge", "LLM compares claim with retrieved passages", "URL must be retrieved; quote must be verbatim"],
    ["Lifecycle check", "LLM only extracts the end-of-life date", "Supported/not decided in code vs today"],
], [0.18, 0.44, 0.38], 14)
footer(s, 6)

# ---- 7. Token optimisation --------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "Fewest tokens", "Measured against a whole-repo baseline")
stat(s, Inches(0.6), Inches(1.8), Inches(2.9), "148", "context tokens for the demo task\n(vs 3,442 whole repo)")
stat(s, Inches(3.7), Inches(1.8), Inches(2.9), "95.7%", "fewer input tokens\non the demo repo", GREEN)
stat(s, Inches(6.8), Inches(1.8), Inches(2.9), "91.0%", "fewer tokens, live,\nprovider-measured (5 files)", GREEN)
stat(s, Inches(9.9), Inches(1.8), Inches(2.9), "~12", "files: whole-repo baseline\nrejected as 'too large'", VIOLET)
panel(s, Inches(0.6), Inches(3.7), Inches(12.2), Inches(2.7), "How", [
    "Hierarchy: repo metadata -> relevant files -> relevant symbols -> exact code excerpts",
    "BM25 retrieval over symbol-level chunks raised recall@3 from 0.143 to 1.0",
    "Per-file chunk cache, invalidated by content hash -> no repeated repo-wide scans",
    "Bounded execution: max model calls, repairs, tool calls, tokens and wall-clock time",
], CYAN, 15)
footer(s, 7)

# ---- 8. Verification results ------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s)
title(s, "Stale-answer detection, verified", "Held-out evaluation against independent ground truth (endoflife.date)")
stat(s, Inches(0.6), Inches(1.8), Inches(2.9), "0", "stale claims passed\nas current", GREEN)
stat(s, Inches(3.7), Inches(1.8), Inches(2.9), "0.714", "accuracy when decided\n(held-out, live)")
stat(s, Inches(6.8), Inches(1.8), Inches(2.9), "2x", "fewer false alarms than\nthe no-LLM baseline", GREEN)
stat(s, Inches(9.9), Inches(1.8), Inches(2.9), "0.933", "status accuracy,\noffline benchmark", VIOLET)
panel(s, Inches(0.6), Inches(3.7), Inches(12.2), Inches(2.7), "Live example", [
    "\"Node.js 18 is the current LTS\" -> Contradicted: end-of-life 2025-04-30, cited source quoted verbatim",
    "\"PostgreSQL 12 is still supported\" -> Contradicted: end-of-life 2024-11-14, cited",
    "\"Water boils at 100 °C at sea level\" -> Not Time-Sensitive: no search spent",
    "Two-step check: the LLM extracts the date, code compares it to today",
], VIOLET, 15)
footer(s, 8)

# ---- 9. Security ------------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "Security by construction", "Enforced in backend code — prompts cannot override it")
panel(s, Inches(0.6), Inches(1.8), Inches(3.9), Inches(4.6), "Confidential repos", [
    "Never sent to remote models, search or caches",
    "No local model -> fails closed",
    "Live demo: malicious 'upload the repo' file -> 0 remote calls, audited",
], CYAN, 14)
panel(s, Inches(4.7), Inches(1.8), Inches(3.9), Inches(4.6), "Approvals + sandbox", [
    "Each approval bound to the exact diff / command",
    "Docker: no network, read-only root, non-root, caps dropped",
    "Verified live against a real Docker daemon",
], VIOLET, 14)
panel(s, Inches(8.8), Inches(1.8), Inches(3.9), Inches(4.6), "Defence in depth", [
    "Prompt-injection scanning; untrusted data stays data",
    "Secret redaction in logs and errors",
    "PBKDF2-hashed passwords, signed tokens",
    "Full audit trail",
], GREEN, 14)
footer(s, 9)

# ---- 10. Reliability + budget -----------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "Reliability and cost control", "Live scenarios, all passing")
table(s, Inches(0.6), Inches(1.8), Inches(12.1), [
    ["Scenario", "What happened (live)"],
    ["Provider outage", "Primary model unavailable -> detected, not retried (4xx), fell back to a healthy model, request preserved"],
    ["Confidential repo", "Repo with a malicious 'upload the repository' instruction -> 0 remote calls, fail closed, audited"],
    ["Budget exhaustion", "Tiny per-task limit -> stopped BEFORE the model call; completed work preserved; resumable"],
    ["Full coding task", "Pagination across backend + frontend + tests -> completed, verified by tests in the sandbox"],
], [0.22, 0.78], 14)
text(s, Inches(0.6), Inches(4.4), Inches(12), Inches(1.6), [
    "Budgets: per request, per task, daily and monthly — enforced in the backend with tracked usage.",
    "Failover: bounded exponential backoff with jitter, provider health registry, security-aware model selection.",
], 15, MUTED)
footer(s, 10)

# ---- 11. Product ------------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "The product", "An AI engineering workstation, not a chatbot")
panel(s, Inches(0.6), Inches(1.8), Inches(6.0), Inches(4.6), "Web dashboard — 9 pages", [
    "Dashboard  ·  Coding Workspace  ·  Answer Verification",
    "Model & Provider Management  ·  Token & Cost Analytics",
    "Evaluation Center  ·  Security & Permissions",
    "Project Repository  ·  Settings & Extensions",
    "Live approvals showing the exact diff",
    "Evidence with sources, dates and conflicts",
], CYAN, 15)
panel(s, Inches(6.8), Inches(1.8), Inches(5.9), Inches(4.6), "Also included", [
    "Versioned REST API (/api/v1)",
    "CLI (verify, context, task, approvals, analytics)",
    "Plugin SDK with host-enforced permissions",
    "SQLite / PostgreSQL persistence",
    "Docker Compose deployment",
    "Full docs: architecture, API, deployment, security",
], VIOLET, 15)
footer(s, 11)

# ---- 12. Quality ------------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "Engineering quality", "Tested at every layer")
stat(s, Inches(0.6), Inches(1.8), Inches(2.9), "151", "pytest tests,\nincl. live Docker", GREEN)
stat(s, Inches(3.7), Inches(1.8), Inches(2.9), "16", "Playwright browser tests\nacross all 9 pages", GREEN)
stat(s, Inches(6.8), Inches(1.8), Inches(2.9), "5", "live demo scenarios\nagainst real services")
stat(s, Inches(9.9), Inches(1.8), Inches(2.9), "100%", "of live-run defects fixed\nwith regression tests", VIOLET)
panel(s, Inches(0.6), Inches(3.7), Inches(12.2), Inches(2.7), "Built honestly", [
    "Never reports success without passing tests; never calls a claim false for lack of evidence",
    "Estimated, mock and unverified values are always labelled in the UI and API",
    "Accuracy measured on a held-out set with independent ground truth",
    "API keys only in a gitignored .env; secret-scanned before every push",
], CYAN, 15)
footer(s, 12)

# ---- 13. Judging criteria ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s); title(s, "Against the judging criteria")
table(s, Inches(0.6), Inches(1.4), Inches(12.1), [
    ["Criterion", "VerityForge"],
    ["Innovation", "Two-step lifecycle check (LLM extracts, code decides); verified citations; scope-aware failover"],
    ["Technical execution", "167 automated tests; live Bifrost, Groq, Gemini, Tavily, Docker; held-out evaluation"],
    ["Problem & impact", "Solves both problem statements: fewer tokens to ship code + evidence-backed AI answers"],
    ["Use of AI", "Agent, evidence judge, routing, RAG, query expansion — each with a deterministic guardrail"],
    ["User experience", "9-page workstation dashboard, live approvals with exact diffs, cited evidence"],
    ["Scalability & potential", "Provider abstraction, versioned API + plugin contract, persistence, Compose deploy"],
], [0.25, 0.75], 14)
footer(s, 13)

# ---- 14. Close --------------------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK); bg(s)
text(s, Inches(0.8), Inches(2.2), Inches(11.5), Inches(1.2), "VerityForge", 60, CYAN, True)
text(s, Inches(0.8), Inches(3.4), Inches(11.5), Inches(0.8),
     "Ship working code on fewer tokens. Trust AI answers with evidence.", 24, WHITE)
text(s, Inches(0.8), Inches(4.6), Inches(11.5), Inches(1.4), [
    "Repository: github.com/iittjjee2024/VerityForge",
    "Run it: README.md  ·  Demo: DEMO.md  ·  Details: SUBMISSION.md",
], 16, VIOLET)
text(s, Inches(0.8), Inches(6.3), Inches(11.5), Inches(0.5), "Thank you", 18, MUTED)

out = Path(__file__).with_name("VerityForge.pptx")
prs.save(out)
print(f"wrote {out} ({len(prs.slides)} slides)")
