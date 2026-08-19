# Decisions & Status — Myntra AI Discovery Engine

**Last updated:** 2026-08-19
**Deadline:** 2026-09-04
**Purpose:** the decisions log and current position. The *rationale* for choices that are stated as facts elsewhere in `Docs/`.

---

## Where we are

| # | Artifact | Status |
|---|---|---|
| 1 | `problemstatement.md` | ✅ v1.1 — requirements, 33-code codebook, segments, ACs |
| 2 | `architecture.md` | ✅ v1 — full technical design, answers all 10 open questions |
| 3 | `edgecase.md` | ✅ v1 — ~90 cases, silent-failure register |
| 4 | `evals.md` | ✅ v1 — per-stage gates, 13 thresholds |
| 5 | `implementationplan.md` | ✅ v1 — 6 phases (P0–P5), gate per phase, schema deltas, gold sampling fix |
| 6 | **P0 — Foundation & Freeze** | ✅ built, gate signed off `evals/reports/gate_P0_20260819.md` — 37/37 checks green; codebook frozen `v1:718e9f3e` |
| 7 | P1 → P5 | ⬜ **next** — P1 Collection & Data Bank. App live: https://myntra-discovery-engine-p62azqwfs4r93yn2rx7qgx.streamlit.app |

**P0 is built.** Repo initialised, schema applied, codebook frozen at `v1:718e9f3e` before any scoring, 37 P0 gate checks green, app shell runs clean. No data collected yet — P1 is blocked on the credentials below.

---

## The build sequence

Four stages, each fully deployed to Streamlit and signed off before the next begins.

| Stage | Ships | Gate |
|---|---|---|
| 1 — Data Bank | Browser, corpus composition, exclusion log | Pilot yield measured (resolves A-1); consensus-preservation test green |
| 2 — Analysis | Cross-tabs, drill-through, validation report | Gold set labelled, AC-9 thresholds met, Z-99 < 15% |
| 3 — Insights | Ranked opportunities, segment recommendation, research artefacts | AC-5, AC-6, AC-7, AC-12 |
| 4 — Chatbot | Grounded Q&A | AC-3, AC-4, injection resistance 100% |

---

## Locked decisions and why

| Decision | Choice | Reasoning |
|---|---|---|
| **Product** | Myntra | User's choice from the three offered |
| **Host** | Streamlit Community Cloud | Free, public URL, Python-native. Its ~1GB RAM ceiling drives the offline/online split below |
| **Provider** | OpenAI throughout | The only API key available. Assignment explicitly permits any AI-native stack, so no compliance risk |
| **Corpus size** | **2,000 relevant records** | ~$18–22 all-in vs ~$40–45 at 5,000. Accepted trade: thin per-code tails and a sparse segment matrix, handled by the minimum-n gate and a fallback to segment × stage |
| **Pipeline location** | Offline on the laptop; Streamlit reads frozen artifacts | Streamlit reruns the whole script on every widget interaction — in-app LLM calls would re-bill on each click. Also gives reproducibility (NFR-3) |
| **Embeddings** | `text-embedding-3-small`, offline only | Needed only for prefilter and clustering. Never ships to Streamlit, so the app carries no ML dependency |
| **Chatbot retrieval** | Code filter + BM25 + routed SQL. **No runtime vectors** | The corpus is already classified into 33 codes — that classification is a better index than semantic similarity, and it keeps the deployed app tiny |
| **Analysis method** | Frontier model, two-pass hierarchical, full stage codebook, `reasoning` retained | The analysis *is* the project. Quality is not traded here |
| **App structure** | Four public sections mirroring the four project parts; **Validation is a tab under Analysis**, not a fifth page | Keeps the public nav at exactly the four parts, and puts the eval numbers beside the analysis they qualify. `9_Label.py` stays hidden and password-gated |
| **Validation** | Full gold set, 150–200 records, labelled in-app | Runs on **pilot** output *before* the full spend, so it debugs the prompt rather than grading it afterwards |

## Amendments made while planning the build (`implementationplan.md` v1)

Three gaps between the design docs, found while sequencing them. All are corrections to `architecture.md`, not new scope.

| # | Gap | Correction | Detail |
|---|---|---|---|
| 1 | Stage 1's exit gate needs a **relevant**-record count, but relevance is a Stage 2 component | Prefilter + relevance built in P1 as an explicitly *provisional* sizing instrument, validated in P2; collect with **+25% headroom** so a later prompt correction cannot drop the corpus below target | plan §3.1 |
| 2 | The gold set is drawn from *pilot output*, so **T-5 prefilter recall and T-2 relevance recall are unmeasurable** — the sample contains only records the filters kept | Gold sampling frame moves to the **raw pilot corpus**, seven strata including 25 prefilter-rejected and 25 LLM-irrelevant records | plan Appendix B |
| 3 | Four schema gaps: `exclusions` as removal vs marking; `secondhand` / `myntra_specific` / `text_available` have no column; `gold` PK blocks the T-13 repeated items; chunked long records have no representation | Fixed in P0's `schema.sql` before any data is written | plan Appendix A |

---

## Source loss — Reddit unavailable (2026-08-19)

**Reddit is out.** Arvind's API application was rejected. Verified: as of 2026 the
self-serve "script" app path at `/prefs/apps` is closed to new developers (redirects
to the policy page or silently fails), and the review form routinely rejects small
personal projects. Retrying is not a fix.

**We do not work around it.** No unauthenticated scraping, no robots.txt circumvention
— NFR-7 commits the project to respecting platform ToS, and R-7/AR-1 already prescribe
"degrade to smaller-but-cited over larger-but-fragile".

**What this costs.** `architecture.md` §5.1 designated Reddit *"Best source for
reasoning. Long-form 'why I didn't buy'"*. It was the only source built for
deliberation rather than reaction. Two consequences that must be carried into every
output:

| Loss | Consequence | Handling |
|---|---|---|
| Long-form reasoning | Fewer records carrying a *chain* of reasoning; counterfactuals ("I'd have bought it if…") and multi-barrier records get scarcer | Target YouTube videos that provoke reasoning; expand curated research |
| Source independence | Play + App Store are highly correlated (both app-store review skew). Effective independent source types drop from ~4 to ~3 | Triangulation rule (§8) weakens — state it; JS-divergence per source becomes more load-bearing, not less |

**Revised source plan:**

| Source | Status | Role |
|---|---|---|
| YouTube (`commentThreads`) | ✅ key verified | **Promoted to primary reasoning source.** Uniquely captures C14 |
| Play Store | ✅ no auth needed | Volume, low yield (EC-COL-13) |
| App Store | ✅ no auth needed | Volume, low yield, correlated with Play |
| Curated research | ✅ agent-sourced | Expanded — now covers the Stage A blind spot *and* part of the community-reasoning gap |
| Reddit | ⛔ unavailable | Gap recorded in corpus composition, per EC-COL-16 |

**Eval amendment:** S1-MET-1 ("each configured source contributed > 0 records | All four")
now reads *all **configured** sources*, with Reddit de-configured and the reason recorded.
An unavailable source must not be silently dropped from the gate — it is de-configured
explicitly, in writing, and shown in the corpus composition dashboard.

---

## Source access — tested empirically 2026-08-19

Every route was tested, not assumed. Results:

| Route | Result | Evidence |
|---|---|---|
| **PRAW / Reddit API** | ⛔ dead | Credentials rejected; self-serve `/prefs/apps` closed to new developers in 2026 |
| **Reddit RSS** (`/r/x/.rss`) | ⛔ dead | HTTP 200 but **zero `<item>` elements** — a block page, not a feed. `search.rss` → HTTP 429 on the first request |
| **Reddit public JSON** | ⛔ dead | `www.reddit.com/…/.json` → **403**. `old.reddit.com/…/.json` → 200 but returns **HTML ("Welcome to Reddit"), not JSON** |
| **Reddit robots.txt** | ⛔ blanket | `User-agent: *` / `Disallow: /` on **both** www and old, plus an explicit Public Content Policy link |
| **Reddit for Researchers** | ⛔ too slow | Sanctioned route, but **months** to approval, academic-project eligibility, delivered via BigQuery. Deadline is 2026-09-04 |
| **Apify / Scrapingdog / Octoparse** | ⛔ **declined** | These function by evading the blanket `Disallow: /`. See below |
| **Myntra on-platform reviews** | ✅ **permitted** | robots.txt: `User-agent: *` / `Allow: /`. 729 disallow rules, **none covering product or review paths** (the only `/buy` rule is `*/buy1-get1-offer/*`). PDP embeds `window.__myx` with ratings + `topReviews` |
| **Quora** | ⛔ disallowed | robots.txt `User-agent: *` → `Disallow: /` (allowlist is only `/`, `/about`, `/press`, `/login`, `/signup`), plus an explicit prohibition on content use for AI/ML systems |

### Why the scraper services are declined

Not a gray area: Reddit publishes `Disallow: /` for all agents, backs it with a stated Public Content Policy, and actively blocks every unauthenticated endpoint. Apify's Reddit Scraper Pro, Scrapingdog and Octoparse work by circumventing exactly that. **NFR-7 in this project's own spec commits it to respecting platform ToS**, and R-7/AR-1 prescribe degrading to smaller-but-cited rather than larger-but-fragile.

There is also a non-ethical argument that matters more to the deliverable: **collection method is a slide in the deck.** "How did you collect this?" is a certain evaluator question in an assignment that grades methodology explicitly. A corpus assembled by paying a proxy service to defeat a site's stated access policy is a worse answer than a smaller corpus with a clean provenance chain and a documented gap.

### Myntra reviews — what they add, and what they do not

Added to the plan. But their analytical role differs from Reddit's, and conflating the two would be a mistake:

- **They do not replace deliberation.** Myntra reviews are post-purchase; the relevance rubric largely excludes post-purchase content. They carry little of the "I've had this saved for two months and keep not buying it" shape Reddit supplied.
- **They do something Reddit could not.** Myntra reviews *are the content* that code **C4** ("real-buyer evidence insufficient") is a complaint about. Collecting them lets C4 be measured **directly** rather than inferred from complaints — review counts, image-review share, and how many reviews the PDP actually surfaces. A sampled product showed `reviewsCount: 13,460`, `reviewsImageCount: 2,434` (18%), and **only 3 top reviews rendered on the page**. That is a quantified C4 finding no complaint corpus could produce.
- **Volume shape:** ~3 visible reviews per product page, so breadth comes from product count (~300–500 products → ~1,000–1,500 reviews), not depth per product.

### Residual gap, stated plainly

Pre-decision deliberation remains under-represented. YouTube comments are the best remaining source for it and are promoted accordingly. **This gap does not fully close, and every output must say so** — it is a known blind spot alongside the Stage A silence already registered in `problemstatement.md` §8.

---

## A-1 RESOLVED — measured relevance yield (2026-08-19)

Assumption A-1 ("sufficient public feedback exists to support meaningful counts")
was the unverified assumption gating the whole project. It is now measured.

| Source | Cleaned | Prefilter pass | Scored | Relevant | **Yield** |
|---|---|---|---|---|---|
| Reddit | 4,389 | 1,183 (27%) | 1,183 | 344 | **29.1%** |
| YouTube | 2,369 | 1,711 (72%) | 1,711 | 481 | **28.1%** |
| Play | 1,452 | 896 (62%) | 896 | 75 | **8.4%** |
| App Store | 429 | 233 (54%) | 233 | 18 | **7.7%** |
| **Total** | **8,639** | **4,023** | **4,023** | **918** | **22.8%** |

Cost: $2.52 (gpt-5-mini), 0 quarantined.

**The app-store prediction was right.** `architecture.md` §5.1 predicted Play and
App Store would show "low relevance yield — mostly delivery/refund", and EC-COL-13
predicted the same. Measured at 8.4% and 7.7% against Reddit's 29.1%, that
prediction holds — and it means the two correlated sources contribute 10% of the
relevant corpus despite being 22% of the cleaned one.

### Two findings that change how results must be reported

**1. Only 35.9% of relevant records are Myntra-specific.** The remaining 64% are
about competitors or online fashion generally. Assumption A-4 ("behaviour discussed
generically transfers to Myntra") is therefore not a footnote — it is load-bearing
for two-thirds of the corpus. Every claim must show its Myntra-specific share, and
a claim resting mostly on non-Myntra records must say so.

**2. 22% of the relevant corpus is Hinglish** (206 of 918 `hi-Latn`, plus 4 mixed).
Keeping code-mixed text untranslated (EC-CLEAN-4, arch §5.3) was not a courtesy —
it preserved a fifth of the evidence base.

### The corpus is below target: 918 relevant vs 2,000

This triggers **P1F**, the one pre-authorised loop-back in `implementationplan.md` §0.4.
At 918 records across 33 codes the leading codes are usable but the tail is thin, and
segment × code will fall below readable n almost everywhere — the fallback to
segment × stage (arch §9.4, EC-INS-8) becomes the primary path rather than a
contingency.

**Preferred remedy is not more collection.** 4,616 records were rejected by the
prefilter and never scored. Scoring them (~$2.60) would both recover relevant records
*and* directly measure prefilter recall — converting EC-PRE-1 from an unmeasured
silent-failure risk into a number. Collecting more raw data does neither.

---

## S2-MET-6 FAILS — the prefilter is dropped from the pipeline (2026-08-19)

EC-PRE-1 was flagged in `edgecase.md` as one of the five worst cases: *"a record
dropped before any LLM sees it is invisible to every downstream metric. There is
no error, no log entry showing a wrong decision, and no way to notice it from the
output."* It is now measured, and it was real.

**Both pools scored — passed AND rejected — so prefilter recall is a fact, not an estimate.**

| Source | Relevant | Prefilter kept | Prefilter dropped | **Recall** |
|---|---|---|---|---|
| YouTube | 573 | 481 | 92 | 83.9% |
| Reddit | 490 | 344 | 146 | **70.2%** |
| Play | 114 | 75 | 39 | **65.8%** |
| App Store | 22 | 18 | 4 | 81.8% |
| **Total** | **1,199** | **918** | **281** | **76.6%** |

**T-5 threshold is ≥95%. Measured 76.6%. FAIL.**

Nearly a quarter of the relevant corpus would have been invisible — and invisible
in the specific way that leaves no trace: not in any denominator, not in any error
log, not detectable from the output.

### Why it failed

Every dropped record had `lexicon_hit=0` and a below-cutoff cosine. They are
relevant by *reasoning*, not by vocabulary — "Best is to get them stitched, it'll
not come within 1k but it'll last many years" is a value-versus-durability purchase
judgement (C6) that shares almost no vocabulary with any exemplar. The embedding
gate was tuned to keep the top 45% by similarity; relevance simply is not that
concentrated in embedding space.

### The decision: drop the prefilter, score everything

The prefilter existed for cost. `architecture.md` §6.1 costed it against
**frontier-model** classification, where scoring 8,639 records would have been
prohibitive. That premise no longer holds:

| | Cost | Relevant recovered |
|---|---|---|
| Prefilter + score survivors | $2.52 | 918 (76.6%) |
| Score everything | ~$5.01 | 1,199 (100%) |

**The prefilter saved $2.49 and cost 281 relevant records.** At gpt-5-mini prices
for a coarse binary task, its economics invert completely. It is removed from the
pipeline; `prefilter.py` is retained only as a diagnostic, and the `prefilter`
table is kept because it is what made this measurement possible.

Corpus is now **1,199 relevant records with 100% coverage of the cleaned corpus** —
no record is unscored, so EC-PRE-1 cannot apply to this run at all.

### Caveat carried forward

Some recovered records look marginal ("Lana Del Rey! so why second thoughts??? go
for it"). The 281 may include relevance false positives, which would mean true
recall is somewhat better than 76.6% and the corpus somewhat smaller than 1,199.
**The gold set is the arbiter** (Appendix B already samples both prefilter-rejected
and LLM-irrelevant strata for exactly this reason). Reported here as measured,
with the uncertainty stated rather than resolved by assertion.

---

## Explicitly rejected

Recorded so they don't quietly reappear as "optimisations":

| Rejected | Why |
|---|---|
| Cheaper model tier for bulk classification | Fine boundary distinctions (C1 fit-uncertainty vs C8 size-unavailable — opposite solves) are exactly where smaller models fail |
| Embedding shortlist of the codebook (33 → 6) | If the true code falls outside the shortlist it can never be assigned, and the failure is invisible in the output |
| Dropping the `reasoning` field | Largest output cost, but it is the audit trail, the input to confusion analysis, and it improves boundary discrimination |
| Free / local models | Not capability — throughput and rate limits. ~50–100h of local generation, or ~12 days on a free API tier, to save ~$15 with 16 days to the deadline |
| Skipping Track B clustering | Saves under a dollar; forfeits the only protection against codebook blindness |

---

## Open items needing the user

| Item | Owner |
|---|---|
| ~~Reddit app registration~~ | ⛔ **Rejected by Reddit — de-configured, see above** |
| YouTube Data API v3 key | ✅ **verified 2026-08-19** — search + commentThreads both working |
| OpenAI credits + hard usage cap | ⚠️ key verified (gpt-5 reachable, live call logged). **$5 loaded — covers through P2C. Top-up to ~$25 needed before the full classification run (P2D).** Hard cap still to be set |
| Gold-set labelling, 150–200 records, ~2–4h in-app | **Arvind** — after Stage 1 pilot |
| Curated research sourcing | **Claude** — with live-URL verification per EC-COL-15 |

---

## Unresolved / to watch

- **A-1 is still unverified** — nobody knows the relevant-record yield rate. The Stage 1 pilot measures it. If yield is very low, source strategy changes before the full run.
- **Segment coverage** may come back too low for a code-level segment matrix; the planned fallback is segment × stage.
- **AC-6 (novel insight)** is a real risk — if the corpus only confirms the 28 pre-registered hypotheses, that must be reported honestly rather than manufactured.
- **Exact OpenAI model IDs and rates** need confirming at build time; all cost figures are estimates until the pilot records actuals in the `runs` table.

---

## Downstream of this engine

The engine is Part 1 of a 7-part assignment. Still to come, and *not* covered by these docs: metric decomposition write-up (Part 2), 5–6 user interviews (Part 3), problem definition (Part 4), **the MVP — a separate deployed product** (Part 5), success metrics (Part 6), risks (Part 7), and a 10-slide deck. The engine informs Parts 2–4; it is not the MVP.
