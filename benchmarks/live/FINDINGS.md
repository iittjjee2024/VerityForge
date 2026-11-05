# Live evaluation findings (dev set)

Gold: endoflife.date API, fetched 2026-11-04. Judge model: groq/openai/gpt-oss-20b via local Bifrost. 3 repeats.
Evidence is recorded (`evidence_cache_dev.json`) and replayed, so reruns cost no Tavily credits.

## Progress on the dev set (judge variant, 14 claims incl. 2 stable controls)

| Run | accuracy_overall | accuracy_when_decided | coverage | stale_passed_as_current | stale_recall |
|-----|------|------|------|------|------|
| baseline | 0.139 | 0.556 | 0.25 | 0.0 | 0.278 |
| fix1 categories (`supported` claims now searched) | 0.167 | 0.60 | 0.278 | 0.0 | 0.333 |
| fix2 `reasoning_effort=low` + lifecycle evidence | 0.472 | 0.708 | 0.667 | 0.0 | 0.611 |

The safety-critical metric — a stale/false claim reported as "Verified Current" — stayed **0.0** throughout.
Stable controls: 6/6 correct every run.

## Fixes applied (with regression tests)

1. "X is still supported" was categorised stable and never searched -> added a `lifecycle` category and freshness policy; added `_SUPPORTS_VERSION` so "supports version N" stays a capability (software_api) claim.
2. gpt-oss models spend hidden reasoning tokens and hit Groq's per-minute token limit -> added `reasoning_effort` passthrough; judge/expansion use `low`. Halved completion tokens.

## Open problems (not yet fixed)

- **"still supported" vs "newest":** the judge marks a supported-but-not-newest version (e.g. Python 3.12) "Potentially Stale". It conflates "a newer version exists" with "this version is unsupported" — different questions. This is the main remaining error source and needs a judge-prompt change (ask specifically about the lifecycle/EOL status, not recency).
- **Rate limits:** ~10/36 judge calls still return 429 even paced at 3 s and with retries, inflating abstentions. A single provider on the free tier is the bottleneck; a second provider or a paid tier would remove it.
- Held-out set (php, ruby, go, ubuntu) is **untouched** and must only be run once, after the above is addressed.

## Later fixes (3 and 4)

3. **Per-category judge guidance** (`judge.GUIDANCE`): lifecycle claims now instruct the model to judge support/EOL status, not recency ("a newer version existing does not make this one unsupported"). No clean measurement yet (see below).
4. **Passage selection bug** (the real cause of the Python-3.12 error): `best_passages` tokenization dropped version numbers, so the retriever often did NOT include the row/sentence about the claim's specific version — the judge was answering without the relevant evidence. Fixed with a `must_include` boost for literal version/name tokens; unit-tested (`test_best_passages_must_include_surfaces_the_specific_version_row`).

## Blocked: Groq free-tier token budget exhausted

Repeated dev-set runs exhausted the Groq free-tier token allowance. The `fix3` run already had 13/36 calls rate-limited; the `fix4` run had **36/36** (every judge call returned 429, so results fell back to the numeric path and are NOT a valid measurement of fixes 3-4). Paced retries at 3-4 s did not help: this is a token/day cap, not a per-minute cap.

**Consequences, stated plainly:**
- Fixes 3 and 4 are implemented and unit-tested but **not yet validated on the live set**.
- The **held-out set has NOT been run** and must not be, until a clean LLM budget is available — running it against a rate-limited provider would burn the one-shot held-out evaluation on noise.

**Diagnosis refined (second session):** the blocker is the Groq free-tier **daily token budget** on the gpt-oss models, not a per-minute rate. Evidence: a single `max_tokens:20` ping returns 200, but any burst of real judge calls returns 429 even after a 70 s wait and even with the judge budget cut from 1200 to 320 tokens (a correct judge answer needs only ~70 completion tokens — verified: "PostgreSQL 15 is still supported" -> supports, citing endoflife.date). Token-cost fix is in place (320-token budget, `reasoning_effort=low`, configurable `EVAL_PACE_SECONDS`) and reduces per-call cost ~4x, but the daily allowance is spent.

**To finish (needs fresh LLM budget — Groq free tier resets daily at 00:00 UTC, or use a 2nd provider / paid tier):**
(a) re-run `--set dev --replay-only --repeats 1` to validate fixes 3-4 on the already-recorded evidence at zero Tavily cost; (b) once dev looks right, run `--set heldout` **once** for the reported figure.

## Second provider added (Gemini) — unblocks Groq, surfaces one more bug

Added Gemini to `bifrost/config.json` (key via `env.GEMINI_API_KEY`) and pointed the judge at
`gemini/gemini-flash-lite-latest` (env `VERITYFORGE_JUDGE_MODEL`); the coding agent still uses Groq. This proves
cross-provider routing through one gateway.

- **Bug found by Gemini (fixed, unit-tested):** Gemini returns `message.content` as a LIST of parts, not a string;
  our adapter did `text.strip()` and crashed. Added `_content_text()` to join text parts (OpenAI spec allows both).
- **Dev run on Gemini (3 repeats, recorded evidence):** judge accuracy 0.417, coverage 0.611, stale-passed-as-current
  **0.0**, controls 6/6. 16/36 verdicts accepted; 15/36 were provider 503 "high demand" (Gemini free tier is flaky
  too), which inflates abstentions.
- **Remaining real limitation (not a bug):** lifecycle claims like "Python 3.12 is still supported" (gold TRUE) are
  judged "Potentially Stale". Even with explicit guidance and version-aware passage retrieval, the small judge model
  conflates "a newer version exists" with "unsupported". Improving this needs a stronger judge model or a two-step
  prompt (extract the version's EOL date, then compare to today) — deferred.

Best measured judge accuracy to date: 0.472 (Groq fix2) / 0.417 (Gemini). Both on the dev set, small sample, both
free tiers rate/availability limited. The held-out set remains unrun pending a stable judge model.

## Two-step lifecycle judge (fix 5-6) — the fix that worked

Instead of asking the model "is this still supported?", the lifecycle path asks it to EXTRACT the end-of-life date
(with a verbatim quote), and the supported/not decision is made in CODE by comparing that date to today. Temporal
reasoning — which the small model got wrong — is removed from the LLM.

- fix5: two-step extraction + deterministic date comparison. Reliability jumped (provider_errors 15 -> 0, consistency
  -> 1.0) but citations were over-rejected.
- fix6 (the key): the model normalises dates to ISO (2027-11-11) while sources render them as "11 Nov 2027". The
  citation check now accepts common date formats (`_date_in_text`), so a correctly-extracted date is no longer
  rejected. Unit-tested with the exact live failure case.

**Dev set after fix6 (judge, 3 repeats, recorded evidence):** accuracy 0.639, accuracy-when-decided 0.793,
coverage 0.806, stale-recall 0.833, **stale-passed-as-current 0.0**, controls 6/6.

## HELD-OUT RESULT (run ONCE, as it should be) — the honest figure

Products php/ruby/go/ubuntu, never used while developing. Judge model gemini-flash-lite-latest, 3 repeats,
8 Tavily credits, gold from endoflife.date fetched 2026-11-04.

| metric | numeric baseline | judge |
|---|---|---|
| accuracy_overall | 0.25 | **0.417** |
| accuracy_when_decided | 0.429 | **0.714** |
| coverage | 0.583 | 0.583 |
| **stale_passed_as_current** | 0.0 | **0.0** |
| false_alarm_rate | 0.667 | 0.333 |
| stale_detection_recall | 0.5 | 0.5 |
| run_to_run_consistency | 1.0 | 1.0 |
| controls | 2/2 | 6/6 |

**Reading it honestly:** held-out accuracy (0.417) is well below dev (0.639) — normal generalisation gap, and the
reason a held-out set exists. The judge roughly halves the false-alarm rate vs the numeric baseline and NEVER passes
a stale/false claim as current (0.0 on unseen data). Most errors are abstentions (lifecycle pages without an
extractable EOL date), i.e. the safe failure mode, not wrong verdicts. When it does decide, it is right 71% of the
time. Sample is small (12 time-sensitive claims x 3); treat as indicative, not a precise rate.

## Honest status

Best *measured* live result so far: dev set, judge variant, fix2 — accuracy 0.472, coverage 0.667, stale-passed-as-current 0.0, stable controls 6/6. Small sample, self-built (independently-labelled) dataset, used to drive fixes. **Not** a headline accuracy claim. The held-out number, run once on a non-rate-limited provider, will be the honest figure, and is still pending.
