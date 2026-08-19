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
| 7 | P1 → P5 | ⬜ **next** — P1 Collection & Data Bank, blocked on credentials |

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
