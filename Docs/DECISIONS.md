# Decisions & Status — Myntra AI Discovery Engine

**Last updated:** 2026-08-20 (end of the P3 session)
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
| 7 | **P1 — Collection & Data Bank** | ✅ built; `S1-HUM-1` (read 30 random records) outstanding |
| 8 | **P2 — Analysis** | ✅ **CLOSED 2026-08-20 — PASS WITH RECORDED LIMITATIONS**, `evals/reports/gate_P2_20260820.md` |
| 9 | **P3 — Insights & Hypotheses** | ✅ **CLOSED 2026-08-20 — PASS**, `evals/reports/gate_P3_20260820.md`. `S3-HUM-1` outstanding |
| 10 | P4 → P5 | ⬜ **next** — P4 the research analyst. ~$2 plus golden-question sweeps |

**P3 is closed.** Addressable population **892 of 1,018** after sizing and excluding C9 (n=21) and segment ① Collectors (n=126). Ranked opportunity **C2 · C1 · C3 · C4 · C4.5**; C2 holds first place in **99.6%** of 1,000 weightings perturbed ±30%. Stage A inversion threshold **6.6×** — the stage ranking is safe. Segment recommendation **④ Stuck Deciders** (392, 43.9%) on a segment × code basis. **AC-6 met: 5 insights confirmed novel by hand**, the headline being that fit uncertainty and approval-seeking are one event rather than two. P3 cost **$0.43** against a $1–2 estimate; running total **$11.40**.

**P2 is closed.** Corpus 12,002 collected → 1,199 relevant → **1,018 analysed** after excluding five low-yield subreddits. Final ranking **C2 13.7% · C6 11.8% · C1 10.8% · C3 8.8% · C7 8.0%**; **Stuck Deciders 38.5%**; Z-99 **12.6%**. Gold set **108 labels + 5 repeats**; Arvind has finished labelling and will not do more, so nothing downstream may assume further human coding. App live: https://myntra-discovery-engine-p62azqwfs4r93yn2rx7qgx.streamlit.app

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

## Tier rejection for classification TESTED and overturned (2026-08-19)

`DECISIONS.md` rejected a cheaper model tier for bulk classification on this
reasoning: *"Fine boundary distinctions (C1 fit-uncertainty vs C8 size-unavailable
— opposite solves) are exactly where smaller models fail."*

That was a **prediction written before anything was built.** It was never measured.
It has now been measured against 47 hand-labelled cases across the codebook's seven
adjacent-code pairs (`evals/fixtures/code_boundary.jsonl`, S2-MET-7 / EC-CLS-12).

| | gpt-5 (minimal) | gpt-5-mini (minimal) |
|---|---|---|
| Correct code assigned | 97.9% | **97.9%** |
| Correct blocking code | 93.6% | 91.5% |
| **C1 vs C8 — the danger pair** | **16/16** | **16/16** |
| C4 vs C14 | 8/8 | 8/8 |
| C6 vs D1 | 6/6 | 6/6 |
| B2.1 vs C8 | 4/4 | 4/4 |
| C3 vs C10 | 4/4 | 4/4 |
| C9 vs C12 | 5/5 | **4/5** |
| A1.1 vs C13 | 3/4 | 4/4 |
| Cost per 1,000 records | $6.37 | **$1.39** |

**The specific claim the rejection rested on is false.** Both models scored 16/16 on
C1 vs C8 — the pair whose confusion would mean "building the wrong thing while the
data appears to agree". Neither confused a solvable Confidence barrier with a
supply-side Eliminator, on any of sixteen constructed cases.

### Where they genuinely differ, and why it matters

`gpt-5-mini`'s single distinguishing miss is **C9** — "just window shopping honestly,
my saved list has 300 things" was coded to Stage A saving behaviour instead of
intent-never-live. C9 is a **denominator control**: per AC-12 and EC-INS-3 it must be
sized and then EXCLUDED from the addressable opportunity, and missing it inflates the
opportunity — the exact error that "survives casual review". Partial mitigation: the
`segment` field captures the same population as S3 independently, so C9 misses are
not the only guard.

`gpt-5`'s own miss (A1.1 coded as A1.2) is arguably a fixture-label problem, not a
model error — "nothing ever reminds me that I saved anything" is a defensible A1.2.

### Standing correction to how this log is used

A line in this file is not evidence. Two cost-driven design choices have now been
tested and both were wrong in the same direction — the prefilter (dropped 23% of the
relevant corpus, kept for a $2.49 saving) and this tier rejection. **Prefer the
measurement to the prediction, including when the prediction is mine.**

---


## P2 session — what was decided and found (2026-08-20)

Five substantive decisions, each with the measurement that forced it.

### 1. Gold frame amended before labelling — `prefilter_rejected` retired

Appendix B allocated 25 of 160 slots to measuring prefilter recall. The
prefilter had already been measured at 76.6% and dropped, so the stratum
bought nothing. **Arvind moved the 25 to `rel_zero` (25 → 50)**, on the
reasoning that relevance is the pass that cannot be re-run affordably ($5.36
against $1.87 for classification) and 7,440 discarded records had never been
read by a human.

### 2. Nine gold labels amended against the frozen definitions (EC-VAL-5)

The first scoring run said **23% of discarded records were actually
relevant**, extrapolating to ~1,700 lost records — more than the entire kept
corpus. Reading the actual disagreements showed eight of nine shared one
mistake: **a positive post-purchase review coded as the doubt-code for the
topic it mentions** ("Very nice. Good fabric" → C2, whose boundary requires
*doubt*). Codes are barriers that BLOCKED a purchase, not topics a comment
touches — and the labelling UI never said so on screen, which makes this a
tool failure as much as a labelling one.

After amendment the figure is **3.2%**. Every amendment records its reason and
the prior label in `gold.notes`. Judgement differences were left alone; only
definitional violations were corrected.

**Lesson: check whether an alarming gold number is a labelling artefact before
acting on it.** Remediation driven by uncalibrated gold tunes the classifier
toward the labeller's errors.

### 3. AC-11 was a pipeline bug, not an incomplete codebook — FR-5.4 overturned

Z-99 sat at 31.7% against a 15% ceiling and `FR-5.4` treated that as evidence
the framework was incomplete. **It was not.** 285 of 380 Z-99 records (75%)
had pass-1 `stages=["Z-99"]`, and `build_code_prompt` skipped Z-99 when
gathering candidates — so pass 2 received **exactly one option** and could not
assign a real code however well the text fitted. It then recorded "does not
match any specific predefined barrier", blaming the codebook for a list it was
never shown.

Two independent signals had agreed before the fix: the gold set (**18 model
Z-99 against 0 human** across 59 jointly-relevant records) and the stored
reasoning naming barriers that are verbatim in existing boundary notes
("pricing fairness" is C6; "four outfits from existing wardrobe" is C3).

Fix: fall back to the full 33-code list when the assigned stages yield no real
candidates. **216 of 380 rescued** (C6 70, C7 51, C2 36, C1 21); **Z-99 →
12.6%, AC-11 PASSES**; no new codes needed.

**The general lesson: a two-pass design makes pass-1 errors absorbing and
invisible. `architecture.md` §6.2 justified two passes on prompt size and
never stated that cost.**

### 4. Twenty-eight evidence-span violations found and fixed (T-6)

23 quoted `thread_context` — the post or video title — instead of the record
body, which on YouTube attributes **another person's words** to this author
(NFR-1). 5 appeared in neither: fabricated or paraphrased. Zero were checker
false positives. T-6 is absolute and on Appendix C's never-cut list, so these
were fixed rather than written up as a limitation. Now 0.

### 5. Five low-yield subreddits excluded — flagged by Arvind, not by the pipeline

He noticed r/mumbai records were mostly not about online fashion. Measured:

| subreddit | scored | relevant | yield | FP rate (gold) |
|---|---|---|---|---|
| IndianFashionAddicts | 544 | 212 | 39.0% | 1 of 5 |
| TwoXIndia | 197 | 73 | 37.1% | 0 of 1 |
| IndianFashion | 100 | 24 | 24.0% | 0 of 1 |
| **mumbai** | 717 | 89 | 12.4% | **4 of 7** |
| **india** | 1,151 | 69 | 6.0% | 2 of 5 |
| **delhi** | 531 | 22 | 4.1% | 0 of 1 |
| **bangalore** | 692 | **1** | 0.1% | — |
| **IndiaTech** | 457 | **0** | 0.0% | — |

Excluded (marked, not deleted). Corpus 1,199 → 1,018. **The ranking did not
move** — every code held position, no share shifted more than 1.5pp — so this
is reportable as a robustness result, not a correction to bury.

Two further faults surfaced doing it:
- **`exclusions` was a marking table nothing read.** `crosstabs.py` selected
  `FROM relevance` directly and never consulted it; `segments.py` had the same
  fault and briefly covered 1,199 records while the ranking used 1,018 — two
  numbers on one screen describing different corpora. Both fixed, with a test
  that the populations agree.
- **r/DesiFashion was configured and collected zero records**, and nothing
  noticed. A silent source failure is indistinguishable from a source with
  nothing to say.

### What P2 leaves failing, on the record

- **T-4 per-code κ** — 2 of 5 measurable codes clear 0.60 (C1 0.66, C6 0.64;
  C3 0.52, C2 0.43, **C10 0.10**). 16 codes are too rare in gold to measure.
- **C10 is unreliable.** The labelling read it as *app* permissions; the
  codebook means **another person's** approval. Any C10 claim needs the caveat.
- **T-2 relevance recall ~79%** vs 85% — an estimate with a stated assumption.
- **T-13 underpowered** — 5 of 20 repeats. The 40% figure must not be quoted.
- **AC-6 novelty OPEN** — cluster labelling never run (budget). Not claimed.

### Metric artefacts worth remembering

**T-3 micro agreement reads 92.8% because it is dominated by true negatives**
across 22 codes. **κ averaged over the same 22 reads median 0.00 because 16
codes appear ≤4 times** — that is "no information", not "no agreement".
Report κ only where gold n ≥ 5. Both artefacts flatter or damn the classifier
for reasons unrelated to its accuracy.

### Cost estimation

I quoted ~$0.60 to re-run 380 records; it cost **$3.41**, because
full-codebook prompts are ~5× longer, not the 2.5× I assumed. **Measure one
record before quoting an LLM batch cost.**

---

## P3 session — what was decided and found (2026-08-20)

### 1. The novelty filter was broken and reported a flattering result

The first AC-6 run flagged **14 of 14 insights as novel** at a hand-picked
similarity threshold of 0.62. That is not a discovery, it is a scale error —
the maximum similarity across all fourteen was 0.476, and the insight that
merely restates the barrier ranking scored the *lowest* of the set with its
nearest prior on an unrelated code.

**Shipping 14/14 would have satisfied AC-6 by broken measurement**, which is
EC-INS-7's failure mode inverted: not manufacturing a novel insight, but
manufacturing the *measurement* that certifies one. Two causes:

- **The priors were four or five words each** — code names, nothing to embed
  against. They now carry name, unresolved question, boundary note and
  observable workarounds.
- **The threshold was chosen rather than measured.** It is now the 5th
  percentile of a control set of 15 deliberate restatements, non-novel by
  construction: they score min 0.402, median 0.681, max 0.750, so the line
  is **0.519**. "Is 0.62 right?" becomes a number anyone can re-run.

The recalibrated filter shortlists 10 of 14; the verdicts are then made **by
hand** and committed to `codebook/novelty_verdicts.yaml` — four of the ten
flagged are recorded there as NOT novel, because similarity separates a
methodological claim from a barrier hypothesis by form regardless of content.

**The general lesson: a filter that fires on everything is not evidence, and
when it fires in the direction you wanted, that is when to check it.**

### 2. AC-6 is met — and the strongest finding rests on the weakest code

**Fit uncertainty and approval-seeking are one event, not two.** C1 and C10
co-occur at lift 2.93 (n_joint 37). The blueprint carries them as separate
entries; nothing in the prior list says a shopper who cannot resolve a size
question outsources the decision to another person, and that the wait for a
reply *is* the deferral. The product consequence inverts what an "approval
barrier" implies — the fix is not a share-and-approve feature, it is removing
the need to ask.

It is corroborated from a direction that never touched the C10 label. Cluster
`all|2` was formed by embedding similarity with no codebook present and named
blind as *"Sizing and measurements questions"*; that one conversation space
holds **113 C1 and 37 C10 records**. Users describe asking-someone as part of
the sizing question. The split is the codebook's, not theirs.

That corroboration is load-bearing, because **C10 is the least reliable code in
the corpus at κ 0.10**. The claim is worth five interviews, not worth building
on — HYP-08 exists to kill it and has the sharpest falsifier of the eight.

### 3. Sub-code shares were double-counted across two pipeline runs

The new roll-up first reported **C2.4 at 120% of C2**. `subcodes` keys on
`run_id`; C2 and C3 were each sub-coded twice after a prompt fix, and the two
runs covered *different populations* (C3: 151 records against 188), so mixing
them is two analyses added together, not a smaller version of the same error.

**Two previously-quoted figures move and the old ones must not be repeated:**

| | previously quoted | corrected |
|---|---|---|
| C2.4 as a share of C2 | 71.5% | **60.6%** |
| C3.1 as a share of C3 | 84.6% | **77.3%** |

Both claims survive; the numbers do not. The Analysis page had the same fault
and now reads the materialised roll-up instead of aggregating the raw table.

### 4. The pipeline reproduced bit-for-bit — an unplanned NFR-3 result

Adding the roll-up meant re-running `crosstabs.py`, recomputing every analysis
table the P2 gate was signed against. All eight reproduced **identical**.
Determinism is measured, not merely intended.

The re-run also made the `published` pin stale, and `test_analysis_populations_agree`
caught it on the next test run. The pin now names every synthesis run behind
the deployed numbers.

### 5. B-5 was being asserted rather than met

The P2 write-up said the gate report was "published to the app's Validation
tab". It was not — the tab held a hard-coded limitations list, and an evaluator
could not read what any gate actually found without cloning the repository. The
Validation tab now renders every `gate_P*.md`, with a test asserting it.

**My recurring failure mode again: asserting a proxy instead of the property.**
A tab existing is not a report being readable.

### 6. Cost, measured rather than estimated

**$0.43 against a $1–2 estimate**, running total $11.40. Breakdown: cluster
labelling $0.153 (21 clusters, gpt-5), insights $0.182 across two passes,
hypotheses $0.092, novelty embeddings $0.0002. The one-record-first discipline
held: the 2-cluster z99 space was labelled first at $0.011 before committing to
the 19-cluster run.

### What P3 leaves as stated limitations

- **`segment_fit` is partly circular.** Segments are derived from the
  classification and "not decided" *is* the presence of a Confidence-phase
  code, so those codes are barred from three of six segments by definition. The
  ranking does not depend on it — the leave-one-out check confirms — and the
  app's slider goes to zero.
- **C6 is over-represented in Play Store reviews**: 52.6% share there against
  20.3% corpus-wide, JS divergence 0.398.
- **The priors are a reconstruction**, not a transcription — the blueprint's
  H/DH prose is not in this repository. Each prior is the union of the claims
  made by the codes that absorbed it, which makes novelty *harder* to claim,
  never easier.
- **Two denominators on adjacent pages.** Analysis uses 1,018; Insights uses
  the addressable 892. Both are labelled, but a reader could conflate them.

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
| **OpenAI budget** | **Arvind.** $11.40 spent. P3 came in at $0.43 against its $1–2 estimate, so the top-up was not needed for it — but P4 needs ~$2 plus golden-question sweeps and the hard cap is still to be set (EC-OPS-3) |
| ~~Gold-set labelling~~ | ✅ **done 2026-08-20 — 108 labels + 5 repeats, 14 skipped.** Arvind has finished and will do no more; **plan nothing that needs further human coding** |
| Curated research sourcing | ✅ 5 items, URLs verified live per EC-COL-15 |
| `S1-HUM-1` — read 30 random records | **Arvind** — outstanding from P1 |

---

## Unresolved / to watch

- ~~A-1 unverified~~ — **resolved**, yields measured per source and per subreddit.
- ~~Segment coverage too low~~ — **resolved** by the v2 derivation: 100% coverage, Stuck Deciders 38.5%.
- ~~**AC-6 is OPEN and unclaimed**~~ — **resolved 2026-08-20.** The 19 `all`-space and 2 `z99` clusters were labelled ($0.153) and reconciled against the codes in `analysis_cluster_code`; **5 insights are confirmed novel by hand**. The filter that certified them was broken first and recalibrated — see the P3 session notes above, because the way it was nearly wrong matters more than the result.
- **The headline novel insight rests on C10, κ 0.10.** It survives on independent blind-cluster corroboration. Treat it as a lead for the interviews, never as a settled finding.
- **T-4 and T-2 fail** and are recorded as failing in the P2 gate report and the app's Validation tab. Do not restate them as passing anywhere downstream.
- **C10 is unreliable (κ 0.10)** — read as *app* permissions by the labeller, defined as **another person's** approval. C10 maps to framework **C4.5**, the Stuck Deciders' most distinctive barrier, so this specifically threatens the sharpest claim in the analysis. Worth re-checking before it reaches the deck.
- **C6 (price/value) rose to #2** after the Z-99 remediation and is the largest barrier that the no-monetary-incentives constraint forbids solving directly. It must be resolved into transparency, anchoring and timing.
- **The 5 low-yield subreddits are excluded but not deleted.** Reversible by removing the `exclusions` rows written by `pipeline/collect/exclude_subreddits.py`.

---

## Downstream of this engine

The engine is Part 1 of a 7-part assignment. Still to come, and *not* covered by these docs: metric decomposition write-up (Part 2), 5–6 user interviews (Part 3), problem definition (Part 4), **the MVP — a separate deployed product** (Part 5), success metrics (Part 6), risks (Part 7), and a 10-slide deck. The engine informs Parts 2–4; it is not the MVP.
