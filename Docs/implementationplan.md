# Implementation Plan — AI-Powered Discovery Engine

**Document status:** v1
**Reads with:** `problemstatement.md` (FR/NFR/AC/R) · `architecture.md` (design) · `edgecase.md` (EC-*) · `evals.md` (S*-INV/MET/PROBE/HUM, T-1…T-13)
**Written:** 2026-08-19 · **Deadline:** 2026-09-04
**Purpose:** the build sequence. Six phases, each with a mechanical exit gate. No phase starts until the previous one is *built, deployed, and signed off*.

---

## 0. Gate discipline

### 0.1 What "built" means

A phase is built when **all five** are true. Four out of five is not four-fifths built; it is not built.

| # | Condition |
|---|---|
| B-1 | Code committed to `main` |
| B-2 | The pipeline stage has **actually run** end-to-end on real data and written a `runs` row |
| B-3 | Artifacts are frozen and committed (`corpus.db`, `artifacts/*.parquet`) |
| B-4 | The corresponding Streamlit page is **live on the public URL** and loads from the frozen artifacts |
| B-5 | `pytest evals/ -m phaseN` is green and `evals/reports/<run_id>.md` is published in-app |

### 0.2 Gate sign-off

Each gate produces one file: `evals/reports/gate_P<n>_<date>.md`, containing the eval table with pass/fail per row, the `run_id` the gate was taken against, actual cost vs estimate, and a one-line verdict. A row is appended to `DECISIONS.md` §Where-we-are. **A gate signed off against a `run_id` that is not the deployed `run_id` is not signed off** (EC-OPS-8 / X-4).

### 0.3 What a failed gate means

| Failure class | Response |
|---|---|
| **Invariant (INV)** | Hard stop. These are logic errors — no threshold to negotiate. Fix and re-run the phase. |
| **Metric below threshold (MET)** | Enter the named remediation loop for that metric. Loops are capped (three iterations for classifier metrics per evals.md §6.2). On cap, the shortfall is **reported as a stated limitation in the app and the deck** — and the phase passes with that limitation recorded. It is never silently dropped. |
| **Absolute threshold (T-6, T-10, T-11)** | Build failure. No limitation clause exists for these. Do not proceed. |
| **Human review (HUM)** | Judgement, recorded with reasoning in the gate report. A "no" here is a real stop. |

### 0.4 The one permitted loop-back

Phase 2A measures the true relevant-record count. If it lands below target, the plan re-enters **Phase 1F (top-up collection)** — the only backward edge in the sequence. It is pre-authorised, scoped (collection only, no schema or codebook change), and must re-pass the Phase 1 gate before Phase 2 resumes. Every other backward movement is a re-plan, not a loop.

### 0.5 App structure — pinned

The four project parts are the four public sections, 1:1. The build order is the nav order, so each phase ships its own page.

| Nav | File | Phase | Public? |
|---|---|---|---|
| *(landing)* | `Home.py` — what this is and how it works. **This is the one-slide (AC-8)** | P5 | Yes |
| Data Bank | `1_Data_Bank.py` | P1 | Yes |
| Analysis | `2_Analysis.py` — **with a Validation tab** rendering the eval report | P2 | Yes |
| Insights & Hypotheses | `3_Insights.py` | P3 | Yes |
| Ask | `4_Ask.py` | P4 | Yes |
| *(hidden)* | `9_Label.py` — gold-set labelling, password-gated | P2 | **No** — EC-OPS-7 |

**Validation is a tab under Analysis, not a fifth page.** Two reasons: the public nav stays at exactly the four project sections, and the validation numbers are read beside the analysis they qualify rather than in a corner of the nav. `Home.py` is written last, in P5, because only then is it true.

---

---

## 1. Timeline

Sixteen days to the deadline, but the engine is Part 1 of seven. **The engine must be finished by 2026-08-30** to leave Parts 2–7 (metric decomposition, 5–6 interviews, problem definition, the MVP, metrics, risks, deck) a workable five days.

| Phase | Days | Target dates | Ships | Gate |
|---|---|---|---|---|
| **P0 — Foundation & Freeze** | 1 | Aug 19–20 | Repo, schema, frozen codebook, creds, eval harness, blank app deployed | P0-1…P0-9 |
| **P1 — Collection & Data Bank** | 3 | Aug 20–23 | Collectors, cleaning, pilot, full corpus, Data Bank page | S1-* + P1-* |
| **P2 — Analysis** | 4 | Aug 23–27 | Relevance, classification, gold validation, clustering, cross-tabs, Analysis page | S2-* + T-1…T-8, T-12, T-13 |
| | | | *⚠️ Sub-phase **2D** (full classification, ~$10 batched) is the first step the current $5 balance cannot fund. Top-up before submitting the batch.* | |
| **P3 — Insights & Hypotheses** | 2 | Aug 27–28 | Ranked opportunities, segment recommendation, research artefacts | S3-* |
| **P4 — Research Analyst (chatbot)** | 2.5 | Aug 28–30 | Grounded Q&A, verification layer, rate limits | S4-* + T-9, T-10, T-11 |
| **P5 — Release & Handoff** | 0.5 | Aug 30 | Home/one-slide, Validation tab published, run pin, walkthrough | X-1…X-4 + AC sweep |
| — | | Aug 31–Sep 4 | *Parts 2–7. Engine frozen.* | — |

### 1.1 Critical path

```
P0 ──▶ P1A pilot collect ──▶ P2A relevance ──▶ P2B GOLD LABELLING (Arvind, 2–4h) ──▶ P2C score
                    │                                        │
                    └──▶ P1E full collect (parallel) ─────────┘
                                                              ▼
                                              P2D full classify (Batch, ≤24h) ──▶ P2E–G ──▶ P3 ──▶ P4 ──▶ P5
```

Two items sit on the critical path and are not controllable by writing code:

- **Gold labelling (P2B)** — 2–4 hours of Arvind's time, and nothing downstream of it can start. It must be scheduled, not hoped for. Book it for **Aug 24–25**.
- **Batch API turnaround (P2D)** — the window is 24h worst case. Submit it **the evening of the day P2C passes**, so the wait overlaps sleep rather than working hours.

### 1.2 Deliberate parallelism

| While waiting on… | Do this |
|---|---|
| Gold labelling (P2B) | Full collection (P1E), curated research sourcing, Track B clustering code (P2E) |
| Batch classification (P2D) | Analysis page scaffolding (P2G), golden-question fixtures for P4 |
| Nothing | The eval harness. It is written *before* the thing it tests, in every phase. |

### 1.3 Blocked on Arvind — resolve before the dates shown

| Item | Needed by | Consequence if late |
|---|---|---|
| Reddit app registration (PRAW client id/secret) | **Aug 20** | Best source for *reasoning* missing; pilot yield unmeasurable for the source that matters most |
| YouTube Data API v3 key | **Aug 20** | C14 (off-platform verification) loses its only native source |
| OpenAI credits + **hard usage cap at $30** | **Aug 20** | No LLM pass can run; and EC-OPS-3 says the cap precedes the first call, not the public URL |
| Gold-set labelling, 150–200 records | **Aug 25** | Full classification spend is unvalidated — AC-9 fails, and every number downstream is undefendable |

---

## 2. Phase 0 — Foundation & Freeze

**Objective:** make every later phase mechanically checkable. Nothing in P0 produces a finding; everything in P0 is what stops a later finding from being wrong.
**Duration:** 1 day · **Cost:** < $0.50 (smoke calls only)

### 2.1 Build tasks

| # | Task | Output |
|---|---|---|
| 0.1 | Repo `myntra-discovery-engine`, venv, `requirements.txt` (app-only: streamlit, pandas, plotly, rank-bm25, openai, pyyaml) and `requirements-pipeline.txt` (praw, google-api-python-client, google-play-scraper, app-store-scraper, datasketch, fasttext, umap-learn, hdbscan, numpy, scikit-learn) | Two dependency files, **never merged** (AR-5) |
| 0.2 | Directory tree exactly as `architecture.md` §3 | Skeleton with `__init__.py` |
| 0.3 | `pipeline/schema.sql` — the arch §4.1 schema **plus Appendix A deltas** | `data/corpus.db` created empty, all invariant queries runnable against it |
| 0.4 | `codebook/codebook_v1.yaml` — all 33 codes with `id, stage, name, phase, outcome, journey_rank, solvable_without_money, question, blueprint_refs, workarounds, boundary_note`; **plus a `contradictions:` block** (EC-CLS-4) | Loads, validates, 33 codes |
| 0.5 | `codebook/segments_v1.yaml` — S1/S2/S3 with positive signals and give-away phrasing (§5.8), threshold 0.6 | Loads |
| 0.6 | **Freeze**: sha256 of both YAMLs recorded as `codebook_version = v1:<hash8>`; a loader that refuses to run if the hash differs from the frozen value without an explicit version bump | FR-5.6 enforced in code, not in prose |
| 0.7 | `pipeline/common/runs.py` — token/cost logger writing a `runs` row per pass, with actual model id and rates confirmed at build time | NFR-4, X-1 |
| 0.8 | Eval harness: `evals/conftest.py`, pytest markers `phase0…phase5`, `evals/report.py` writing `evals/reports/<run_id>.md` | `pytest evals/ -m phase0` green |
| 0.9 | **Fixtures authored by hand, now** — `dedupe_consensus.jsonl` (40 distinct-author near-identical + 5 same-author repeats), `relevance_boundary.jsonl` (60 cases, half of them EC-REL-1 past-experience boundary), `injection_records.jsonl` (6 payloads per evals §8.3) | Three files, hand-written, committed |
| 0.10 | `app/Home.py` — placeholder page. Deploy to Streamlit Community Cloud **today** | Public URL live on day 1 |
| 0.11 | Credentials: Reddit app, YouTube key, OpenAI key in `.streamlit/secrets.toml` (gitignored) + **hard usage cap $30 set in OpenAI billing** | All four smoke-tested |

### 2.2 Why the blank app deploys on day 1

The deploy path is the single most common late-stage surprise in a Streamlit project: dependency resolution failures, cold-start timeouts, secrets not propagating (AR-5, EC-OPS-1). Discovering that on Aug 29 with a chatbot to ship is a project-ending problem; discovering it on Aug 20 with a blank page is twenty minutes. **Every phase after this one deploys to a URL that is already known to work.**

### 2.3 Exit gate — P0

| ID | Type | Check | Threshold |
|---|---|---|---|
| P0-1 | INV | `schema.sql` applies clean to an empty DB; every table in arch §4.1 + Appendix A exists | Exact |
| P0-2 | INV | Codebook loads; **33 codes**; every code has non-empty `boundary_note`, `journey_rank`, `phase`, `outcome`, `solvable_without_money` | 33/33, no nulls |
| P0-3 | INV | `journey_rank` is a total order with no ties within a stage (blocking-code determination depends on it — arch §7.1) | 0 ties |
| P0-4 | INV | Contradiction block present and symmetric; C9 and C11 mutually exclusive with every Confidence-phase code | Asserted |
| P0-5 | INV | Codebook hash frozen and recorded; loader rejects a mutated file | Raises |
| P0-6 | MET | All four collectors authenticate and return ≥1 record in a smoke fetch | 4/4 |
| P0-7 | MET | One 1-record OpenAI call succeeds and writes a `runs` row with real token counts and cost | Row exists |
| P0-8 | OPS | OpenAI hard usage cap set at **$30** — evidenced by screenshot in the gate report | Set **[EC-OPS-3]** |
| P0-9 | OPS | Blank app live at a public URL; cold start timed and recorded | < 30s |

**Do not start P1 until:** all nine green. P0-6 failing on Reddit or YouTube is a credentials block on Arvind, not a code problem — escalate immediately rather than building around it.

---

## 3. Phase 1 — Collection & Data Bank

**Discharges:** FR-1.1…FR-1.6, A-1 · **Duration:** 3 days · **Cost:** ~$1–2 (embeddings + pilot relevance)

### 3.1 The dependency this phase resolves

`architecture.md` §5.5 sets the Stage 1 exit gate at "2,000 **relevant** records collected". Relevance is determined by an LLM pass that belongs to Stage 2. The gate as written cannot be taken.

**Resolution.** The prefilter and relevance pass are *built and run in P1 as a provisional sizing instrument*, explicitly unvalidated. They are *validated* in P2 against the gold set. The consequence is stated openly rather than hidden:

- If P2 validation changes the relevance prompt materially, the P1 sizing was computed on a different filter and the relevant count shifts.
- **Mitigation:** collect with **+25% headroom** over the yield-derived target. A relevance prompt correction that costs 20% of the corpus then still lands above 2,000, and the top-up loop (P1F) never fires.
- The provisional relevance labels are written under their own `run_id` and are **superseded, not amended**, by the validated run. No number is ever computed from a provisional label.

### 3.2 Build tasks

| # | Task | Notes |
|---|---|---|
| 1.1 | `collect/play_store.py`, `app_store.py`, `youtube.py` — all emitting the same `records` schema, all writing `collect_query`. **`reddit.py` is written but de-configured** (API access rejected 2026-08-19, see `DECISIONS.md`); it activates if credentials ever arrive | Per-source checkpointing on `ingest_run_id`; resume by diffing `native_id` (EC-COL-3). Never overwrite a partial run |
| 1.2 | Per-source and per-video yield logging | EC-COL-1, EC-COL-2 — a source or video contributing zero is **logged**, never skipped quietly |
| 1.3 | `clean/dedupe.py` — exact hash dedupe **across** sources (safe); near-dupe MinHash Jaccard > 0.85 **within `(source, author_hash)` only** | **EC-CLEAN-1. The single most consequential line in the build.** Cross-author similarity is *computed and stored as a consensus metric*, never used to remove |
| 1.4 | `clean/language.py` — fasttext langid; Latin script + Hindi lexicon markers → `hi-Latn`; **never drop on language** | EC-CLEAN-4/5. `lang` is metadata; `unknown` is valid |
| 1.5 | `clean/scrub.py` — PII to typed placeholders `[ORDER_ID]`, `[PHONE]`, `[EMAIL]`; author → salted hash | EC-CLEAN-3, NFR-7. Placeholders, not deletion — sentence structure survives |
| 1.6 | Normalise into `text_clean`; **`text_raw` preserved verbatim and is what the classifier reads** | EC-CLEAN-6 — ALL CAPS and `!!!!` carry the `intensity` signal |
| 1.7 | `exclusions` as a **marking table**, not a removal — every collected record stays in `records` | See Appendix A.1. Required for FR-1.5/1.6 (browsable exclusion log) and for the gold sampling frame (Appendix B) |
| 1.8 | **P1A — Pilot collect: ~1,500 raw, deliberately spread thin across all four sources** | arch §5.2. A pilot drawn mostly from Play Store measures the wrong thing |
| 1.9 | `classify/prefilter.py` — lexicon gate ∪ embedding gate (cosine vs ~50 hand-written exemplars). **Union, never intersection** | EC-PRE-1. Every prefilter decision is persisted so recall can be measured later |
| 1.10 | `classify/relevance.py` — LLM pass 0, provisional. Rubric carries the EC-REL-1 carve-out with worked examples both directions | Run synchronously on the pilot (small n, no 24h wait) |
| 1.11 | **P1C — Yield report per source.** Relevant ÷ collected, per source. **This resolves A-1** | The number that sizes everything downstream |
| 1.12 | **P1E — Full collection** sized from measured yield × 1.25 headroom | Runs in parallel with P2B gold labelling |
| 1.13 | `collect/curated.py` — 15–25 research items on Indian online fashion behaviour, cart abandonment, return rates. **Every one live-URL verified at collect time** | EC-COL-15. Agent-sourced, so the check is mandatory. Paywalled/image-only → citation + abstract, `text_available = false`, never quoted (EC-COL-14) |
| 1.14 | `app/lib/db.py` (cached read-only conn), `app/lib/charts.py` (colour-blind palette, **n always rendered**), `app/lib/citations.py` | Reused by every later page |
| 1.15 | `app/pages/1_Data_Bank.py` — filter, full-text search, record detail with provenance, **corpus composition dashboard**, **exclusion log** | FR-1.5/1.6. Composition is evidence for the §8 source-bias caveats, not decoration |
| 1.16 | **Distinct-author count rendered beside every record count**, everywhere | EC-COL-9. "200 records from 12 authors" is a different claim from "200 records from 180 authors" |
| 1.17 | Deploy | B-4 |

### 3.3 Exit gate — P1

| ID | Type | Check | Threshold |
|---|---|---|---|
| S1-INV-1 | INV | Accounting identity: `count(collected) == count(retained) + count(excluded)` | Exact — no record vanishes unlogged |
| S1-INV-2 | INV | Every record has non-empty `source_url` and `text_raw` | 100% |
| S1-INV-3 | INV | `record_id` unique; re-ingest idempotent | 100% **[EC-CLEAN-7]** |
| S1-INV-4 | INV | No email/phone pattern survives in `text_clean` | 0 hits |
| S1-INV-5 | INV | Every exclusion row carries a reason from the allowed enum | 100% |
| S1-MET-1 | MET | Each **configured** source contributed > 0 records. De-configured sources are named, with the reason, in the gate report and the corpus composition dashboard — never silently dropped | 3/3 + curated **[EC-COL-1, EC-COL-16]** |
| S1-MET-2 | MET | Curated citations resolve to a live URL | **100%** **[EC-COL-15]** |
| S1-MET-3 | MET | Distinct-author count computed and displayed per source | Present |
| **S1-PROBE-1** | PROBE | **Consensus-preservation.** Run cleaning over `dedupe_consensus.jsonl`: **all 40 distinct-author records survive**, and **4 of the 5 same-author repeats are removed** | Both directions **[EC-CLEAN-1]** |
| S1-HUM-1 | HUM | Read 30 random retained records — are they what you expected? | Judgement |
| **P1-1** | MET | **Pilot yield reported per source. A-1 resolved.** Projected relevant = Σ(raw × yield) ≥ 2,000 with headroom, or a descope decision is recorded in `DECISIONS.md` | Reported either way |
| P1-2 | INV | Near-dedupe is author-scoped — verified by code inspection **and** S1-PROBE-1 | Both |
| P1-3 | INV | Cross-author similarity stored as a consensus metric, not applied as a filter | Column populated |
| P1-4 | OPS | App deployed; Data Bank loads from frozen artifacts; cold start recorded | < 30s |
| P1-5 | INV | Every prefilter and relevance decision persisted with `run_id` (needed for Appendix B) | 100% |
| **P1-6** | INV | **Source-independence caveat recorded.** Play and App Store are correlated (both app-store review skew), so with Reddit gone the corpus carries ~3 independent source types, not 4. The triangulation rule (`problemstatement.md` §8) and the evidence-strength `source_diversity` term must both be computed against *independent* types, not raw source count | Stated in composition dashboard |

**Do not start P2 until:** all green, **and** P1-1 has an actual number. A-1 is the assumption that gates the project; leaving it unmeasured and proceeding is the single largest process risk in the plan.

**P1F — top-up collection (pre-authorised loop-back).** Fires only if P2A's validated relevant count < 2,000. Scope: collection re-run against the highest-yield sources only. No schema, codebook, or prompt change. Must re-pass this gate.

---

## 4. Phase 2 — Analysis

**Discharges:** FR-2.1…2.6, FR-5.1…5.7, AC-9, AC-10, AC-11 · **Duration:** 4 days · **Cost:** ~$14–18

The heaviest gate in the project. Every number in Phases 3, 4, and the deck inherits these labels.

### 4.1 Sub-phase order — and why it is not negotiable

**Label the pilot, fix the prompt, then spend the full budget.** Finding a broken code boundary after classifying the full corpus means paying twice and, worse, means the gold set graded the pipeline instead of debugging it.

| Sub | Task | Blocking? |
|---|---|---|
| **2A** | Validated relevance run on pilot; **true relevant count established** → P1F decision point | Yes |
| **2B** | Gold sampling (Appendix B) + `9_Label.py` + **Arvind labels 150–200 records in two sittings, 20 repeated** | **Yes — human critical path** |
| **2C** | Score against gold; confusion matrix; remediation loop (cap 3) | Yes |
| **2D** | Full-corpus classification via **Batch API**, submitted overnight | Yes |
| **2E** | Track B clustering (built during 2B/2D waits) | No |
| **2F** | Track C reconciliation + derived analytics + cross-tab materialisation | Yes |
| **2G** | `2_Analysis.py` (incl. Validation tab) + deploy | Yes |

### 4.2 Build tasks

| # | Task | Notes |
|---|---|---|
| 2.1 | `classify/stage.py` — LLM pass 1, output `A\|B\|C\|D` (multi) or `Z-99` | Small prompt, cheap, high accuracy |
| 2.2 | `classify/codes.py` — LLM pass 2, **codes within assigned stage only** (≤14, not 33), carrying the **full `boundary_note` for every candidate** | arch §6.2. Boundaries are where classification fails |
| 2.3 | Structured outputs, JSON schema `strict: true`; **retain the `reasoning` field** | Largest output cost; it is the audit trail (NFR-4), the input to confusion analysis, and it measurably improves boundary discrimination |
| 2.4 | Long-record chunking at classification time only — chunk > ~2,000 tokens on paragraph boundaries, classify each, **union the codes** | EC-COL-5. **Chunks are not rows in `records`** — see Appendix A.4 |
| 2.5 | `classify/batch.py` — Batch API driver, ~500-record chunks, resume by diffing `records` against `classifications` on `run_id` | EC-CLS-13, AR-4 |
| 2.6 | Write-time asserts: zero codes → forced `Z-99` (EC-CLS-1); contradiction check (EC-CLS-4); `evidence_span` exact-substring check (EC-CLS-6); Eliminator ⇒ exit consistency (EC-CLS-5) | These run **at write time**, not at review time |
| 2.7 | Segment inference at threshold **0.6**; below → `unknown`; **coverage % stored, not inferred at render** | EC-CLS-10, S2-INV-10 |
| 2.8 | `validate/goldset.py` — stratified sampling per **Appendix B**, scoring, per-code κ, **confusion matrix with the C1↔C8 cell named** | EC-CLS-12, the known danger pair |
| 2.9 | `app/pages/9_Label.py` — password-gated, two-sitting flow with 20 records silently repeated | EC-VAL-1, EC-OPS-7 |
| 2.10 | `cluster/embed.py` + `cluster/discover.py` — `text-embedding-3-small` → UMAP(15, 0.0, 10) → HDBSCAN(min_cluster_size = max(15, n/200)) → LLM labelling **blind to the codebook** | EC-CLU-4. Fixed seeds (EC-CLU-3). `embeddings.npy` gitignored, never deployed |
| 2.11 | **Z-99 clustered separately** | The FR-5.4 mechanism for proposing new codes |
| 2.12 | `analyse/reconcile.py` — cluster × code contingency, entropy both directions | Code→many clusters = too coarse; cluster→many codes = boundary wrong; cluster with no dominant code = new territory (feeds AC-6) |
| 2.13 | `analyse/derived.py` — co-occurrence lift + PMI with min-support guard, blocking code by `journey_rank` minimum, counterfactual mining, workaround intensity, Jensen–Shannon source divergence, intensity × prevalence, evidence-strength composite | arch §6.5 |
| 2.14 | `analyse/crosstabs.py` — materialise all ten `analysis_*` tables, each carrying `n` and `run_id` | **The app performs no aggregation over raw records.** Charts and chatbot read the same rows and therefore cannot disagree |
| 2.15 | **Minimum-n gate as a shared library function**: n ≥ 30 for a ranked claim, n ≥ 15 to appear at all; below → greyed with the count shown | arch §9.4, AR-12. Used identically by charts (P2) and chatbot (P4) — EC-CHAT-5 |
| 2.16 | `2_Analysis.py`, with a **Validation tab** rendering `evals/reports/<run_id>.md` in-app. **Not a separate top-level page** — the public nav stays at the four project sections (Data Bank · Analysis · Insights · Ask), and the validation numbers are read beside the analysis they qualify | evals.md §4. "How do you know your classifier is right?" gets a URL, not a claim |

### 4.3 Remediation loop (T-1 / T-3 failure)

```
score against gold → read confusion matrix → sharpen the worst boundary_note
→ bump prompt_version → re-run PILOT only → re-score
```
**Maximum three iterations.** A pilot re-run costs a few dollars, so the loop is affordable; the cap exists so it does not become a time sink against a fixed deadline. On the third failure, the shortfall is reported as a stated limitation in the app and the deck (EC-VAL-3) and the phase passes with that limitation on record.

### 4.4 Exit gate — P2

**Invariants** — all must be 0 violations or 100%:

| ID | Check | Ref |
|---|---|---|
| S2-INV-1 | No relevant record has zero codes | EC-CLS-1 |
| **S2-INV-2** | **Every `evidence_span` is an exact substring of `text_raw`** (whitespace-normalised) | **T-6 — absolute, no tolerance.** EC-CLS-6 |
| S2-INV-3 | No contradictory code pair (C9/C11 × any Confidence-phase code) | EC-CLS-4 |
| S2-INV-4 | `blocking_code` phase consistent with `outcome` (Eliminator ⇒ exit) | EC-CLS-5 |
| S2-INV-5 | `codebook_version` uniform within a `run_id` | EC-CLS-16 |
| S2-INV-6 | Every code in `classifications` exists in the codebook | — |
| S2-INV-7 | **All 33 codes appear in `analysis_code_prevalence`, including zero-count** | T-8 / AC-10 |
| S2-INV-8 | Z-99 share < 15% | T-7 / AC-11 |
| S2-INV-9 | Every `analysis_*` row carries `n` and `run_id` | — |
| S2-INV-10 | Segment coverage % stored, not inferred at render | EC-CLS-10 |

**Metrics against gold** (run on **pilot** output, before the full spend):

| ID | Metric | Threshold |
|---|---|---|
| S2-MET-1 | Relevance accuracy | **T-1 ≥ 80%** |
| S2-MET-2 | Relevance **recall** | **T-2 ≥ 85%** — a missed relevant record is invisible downstream |
| S2-MET-3 | Relevance precision | Reported, no floor |
| S2-MET-4 | Per-code exact agreement | **T-3 ≥ 70%** |
| S2-MET-5 | Cohen's κ per code where n permits | **T-4 ≥ 0.60** |
| S2-MET-6 | **Prefilter recall** — of gold-relevant records, how many would the prefilter have kept? | **T-5 ≥ 95%** **[EC-PRE-1]** — *measurable only with the Appendix B sampling frame* |
| S2-MET-7 | **C1↔C8 cross-assignment**, reported by name | ≤ 15% **[EC-CLS-12]** |
| S2-MET-8 | Relevance accuracy on `relevance_boundary.jsonl` (past-experience cases) | ≥ 75% **[EC-REL-1]** |
| S2-MET-9 | Intra-rater agreement on the 20 repeated gold items | **T-13 ≥ 85%** **[EC-VAL-1]** |

**Clustering:**

| ID | Check | Threshold |
|---|---|---|
| S2-CLU-1 | HDBSCAN noise fraction | < 60%, else **declare Track B weak and say so** [EC-CLU-1] |
| S2-CLU-2 | Determinism — run twice with fixed seed | **T-12 100%** |
| S2-CLU-3 | No single cluster holds > 50% of clustered records | Else re-tune |
| S2-CLU-4 | Cluster labelling prompt verified **blind to the codebook** | Prompt inspection [EC-CLU-4] |

**Human review:** S2-HUM-1 (20 highest- and 20 lowest-confidence classifications) · S2-HUM-2 (every Z-99 cluster label — is a real code hiding there?) · S2-HUM-3 (top 10 co-occurrence pairs by lift — genuine compound barriers?).

**Do not start P3 until:** every invariant green, T-1…T-5, T-7, T-8, T-12, T-13 met (or a capped-loop limitation formally recorded), C1↔C8 reported by name, human review done, Validation tab live.

---

## 5. Phase 3 — Insights & Hypotheses

**Discharges:** FR-3.1…3.5, AC-5, AC-6, AC-7, AC-12 · **Duration:** 2 days · **Cost:** ~$1–2

### 5.1 Build tasks

| # | Task | Notes |
|---|---|---|
| 3.1 | `synthesise/insights.py` — generates over the **`analysis_*` tables, never raw records** | Every insight must cite a table row; uncitable → rejected (EC-INS-6) |
| 3.2 | `synthesise/hypotheses.py` — each hypothesis carries supporting count, verbatims, source diversity, confidence, **contradicting evidence**, and **what would disprove it** | AC-7 |
| 3.3 | Opportunity score `w₁·prevalence + w₂·intensity + w₃·defer_share + w₄·solvable_without_money + w₅·evidence_strength + w₆·segment_fit` | arch §7.2 |
| 3.4 | **Weights as live sliders in the app**, with a sensitivity panel | A ranking that survives the sliders is a far stronger claim than one asserted. It also answers "why those weights?" before it is asked |
| 3.5 | **C9 and S3 sized, then excluded** from the addressable opportunity | AC-12, EC-INS-3. Leaving them in inflates the opportunity — the easiest way to produce a wrong answer that survives casual review |
| 3.6 | **Stage A inversion threshold panel** — how far Stage A would have to be under-reported to overtake the leading stage | arch §7.3. Turns an acknowledged bias into a quantified sensitivity. A threshold of 2–3× means the conclusion is fragile and must be stated as such (EC-INS-4) |
| 3.7 | Segment recommendation from segment × code; **pre-planned fallback to segment × stage** if the matrix is too sparse | EC-INS-8, arch §9.4 — expected at 2,000 records |
| 3.8 | `synthesise/artefacts.py` — interview guide (5–6 interviews, Part 3), survey instrument, problem-framing canvas, each pre-populated with top hypotheses and falsifiers | FR-3.4 |
| 3.9 | `3_Insights.py` + deploy | — |

### 5.2 Exit gate — P3

| ID | Type | Check | Threshold |
|---|---|---|---|
| S3-INV-1 | INV | Every insight cites an `analysis_*` row **that exists** | 100% **[EC-INS-6]** |
| S3-INV-2 | INV | Every hypothesis has a non-empty falsifier | 100% **AC-7** |
| S3-INV-3 | INV | Every hypothesis records contradicting evidence (possibly "none found") | 100% |
| S3-INV-4 | INV | C9 and S3 sized, then excluded from opportunity totals | Asserted **AC-12** |
| S3-INV-5 | INV | No opportunity ranked on n below the minimum-n floor | 0 violations |
| S3-MET-1 | MET | **Novelty — ≥1 insight not matching H1–H15 / DH1–DH13** | **AC-6** |
| S3-MET-2 | MET | Weight-robustness Monte Carlo: perturb six weights ±30%, 1,000 draws, report share of weightings preserving the top rank | Reported, no floor |
| S3-MET-3 | MET | Stage A inversion threshold computed and displayed **on the chart itself** | Present |
| S3-HUM-1 | HUM | Would you defend this opportunity choice to a sceptical mentor using only this evidence? | Judgement |

**On S3-MET-1.** Automated first pass: embed each generated insight and each of the 28 pre-registered hypotheses, flag any insight whose maximum similarity falls below threshold. **Confirm by hand — similarity is a filter, not a verdict.** If nothing clears it, check the Z-99 clusters and the cluster↔code reconciliation first, since novelty usually hides there. If it still clears nothing, **the honest report is that the corpus confirmed existing priors** (EC-INS-7). Manufacturing a novel insight to satisfy AC-6 is the worst available outcome — it is precisely the confirmation theatre R-1 exists to prevent, inverted.

**Do not start P4 until:** all invariants green, novelty resolved *either way in writing*, robustness reported, S3-HUM-1 answered.

---

## 6. Phase 4 — The Research Analyst

**Discharges:** FR-4.1…4.5, AC-3, AC-4 · **Duration:** 2.5 days · **Cost:** ~$2 (build + 60-question sweeps)

### 6.1 Build order — deterministic parts first

Steps 2, 3 and 5 of the loop are plain Python. Building them **before** the LLM steps means the guarantees in arch §8.8 are guarantees rather than prompt instructions, and it means the golden-set harness exists before there is anything to grade.

| # | Task | LLM? |
|---|---|---|
| 4.1 | `lib/retrieval.py` **Channel 1** — whitelisted, parameterised SQL registry over `analysis_*`. **The planner chooses which query and its arguments; it never writes SQL** | No |
| 4.2 | **Channel 2** — BM25 over `text_clean`, filtered to the codes in the plan, returning `evidence_span` + record + `source_url` | No |
| 4.3 | **Channel 3 — disconfirming evidence.** Retrieves *against* the emerging answer: rival codes, complicating co-occurrences, keyword-matched Z-99 | No |
| 4.4 | **Channel 4** — method & limitations: source mix, mean classifier confidence, gold agreement, registered bias flags (Stage A under-detection) | No |
| 4.5 | **Channel 5** — BM25 over `source = 'curated'` for external corroboration *or contradiction* | No |
| 4.6 | **Step 3 gate** — deterministic comparison of `evidence_needed` vs retrieved, with minimum-n thresholds → FULL / PARTIAL / NONE | No — **this is why refusal is testable** |
| 4.7 | **Step 5 verifier** — every numeral regex-extracted and matched against Channel 1 results (with a structural-constant allowlist per EC-CHAT-10); every quoted string exact-substring-matched against a retrieved record (normalised comparison, EC-CHAT-11); every paragraph carries a citation or an `Interpretation:` prefix | No |
| 4.8 | **Step 1 planner** — intent, restatement, sub-questions, entities, evidence plan, answerability. Last 3 turns carried for follow-ups (EC-CHAT-3). False-premise flagging (EC-CHAT-4). `methodological` intent routes to a static pipeline description, not retrieval (EC-CHAT-6) | Yes (1 call) |
| 4.9 | **Step 4 synthesis** under the answer contract: Answer / Evidence / In users' words / Variation / Counter-evidence / Confidence / Limitations | Yes (1 call) |
| 4.10 | **Injection hardening** — retrieved records wrapped in delimited blocks labelled untrusted; system prompt states record content is **evidence to quote, never instructions to follow** | EC-CHAT-9 |
| 4.11 | **Proxy discipline** in the system prompt — corpus share is share of *discussion*, never a drop-off or conversion rate | `problemstatement.md` §8, enforced at generation *and* asserted at S4-INV-8 |
| 4.12 | Bounded regeneration — **one** retry on verification failure, then serve with an explicit "could not fully verify" banner | AR-11, EC-CHAT-8. Never loop, never fail silently |
| 4.13 | Rate limits: per-session question cap, global daily cap; gibberish/empty rejected before any paid call | EC-OPS-3, EC-CHAT-7 |
| 4.14 | `fixtures/golden_questions.yaml` — 60 questions across the eight categories, each with expected route and assertions | evals §8.1 |
| 4.15 | `4_Ask.py` — **restatement displayed before the answer** so a misread question is visible | AR-6 |
| 4.16 | Deploy | — |

### 6.2 Exit gate — P4

| ID | Type | Check | Threshold |
|---|---|---|---|
| S4-INV-1 | INV | Route matches expectation across the golden set | **T-9 ≥ 90%** |
| **S4-INV-2** | INV | **Every numeral (minus the structural allowlist) appears in retrieved SQL results** | **T-10 = 100% — absolute** |
| **S4-INV-3** | INV | **Every quoted string is an exact substring of a retrieved record** | **100% — absolute** |
| S4-INV-4 | INV | Required sections present — Confidence, Limitations | 100% |
| S4-INV-5 | INV | Every paragraph carries a citation or an `Interpretation:` prefix | 100% |
| S4-INV-6 | INV | FULL answers cite ≥1 record **and** ≥1 analysis row | 100% |
| S4-INV-7 | INV | NONE answers make no factual claim about the corpus | 100% |
| S4-INV-8 | INV | No answer states a corpus share as a drop-off or conversion rate | 0 violations |
| **§8.3** | PROBE | **Injection: 6 payloads retrieved into context are treated as evidence to quote, never as instructions** | **T-11 = 100% — absolute. Any compliance is a build failure, not a tuning issue** |
| S4-OPS-1..5 | OPS | Session cap · daily cap · $30 hard cap live **before the URL is shared** · missing key degrades to a message not a stack trace · gibberish rejected pre-call | All |
| S4-HUM-1 | HUM | Read all 10 canonical answers. Useful to a PM, or merely correct? | Judgement |
| S4-HUM-2 | HUM | Do the PARTIAL answers **name** the gap, or gesture at it? | Judgement |
| S4-LLM-1 | — | LLM-as-judge groundedness/completeness — **advisory only, recorded as the weakest signal in the report** | Advisory |

**Category coverage is the point, not question volume.** One out-of-scope question tests the same code path as ten. If the golden set must shrink, shrink within categories, never by dropping one.

**Do not start P5 until:** T-9 ≥ 90%, **T-10 and T-11 at 100%**, all per-answer invariants green, rate limits and spend cap live, both human reviews done.

---

## 7. Phase 5 — Release & Handoff

**Duration:** 0.5 day · **Cost:** ~$0

| # | Task | Ref |
|---|---|---|
| 5.1 | `Home.py` — what this is and how it works, in one screen. **This is the one-slide (AC-8)**, and it is written last because only now is it true | AC-8 |
| 5.2 | Validation tab (under Analysis) publishes the full eval report for the pinned `run_id` | NFR-4 |
| 5.3 | **Pin the published `run_id`.** The app reads a pinned run, never "latest" | **EC-OPS-8 / X-4** — a pipeline re-run mid-demo must not change what an evaluator sees |
| 5.4 | Cost reconciliation: actual tokens and spend per pass from `runs` vs `architecture.md` §9 estimate | X-1 |
| 5.5 | Full pipeline re-run reproduces identical counts | X-2 / NFR-3 |
| 5.6 | **Cold walkthrough** — hand the URL to someone with no context. Can they browse the Data Bank, read the analysis, find a hypothesis, and ask a question unassisted? | AC-1 |
| 5.7 | AC-1…AC-12 coverage sweep — every AC maps to a **passing** eval | X-3 |
| 5.8 | Warm the app before any demo | EC-OPS-1 |

### 7.1 Exit gate — P5

| ID | Check |
|---|---|
| X-1 | Actual vs estimated cost reported |
| X-2 | Re-run reproduces identical counts |
| X-3 | Every AC-1…AC-12 maps to a passing eval |
| X-4 | App pins a published `run_id`; charts and chatbot read the same run |
| P5-1 | Cold walkthrough completed by someone other than Arvind, unassisted |
| P5-2 | Engine frozen. `DECISIONS.md` updated. Parts 2–7 begin |

---

## Appendix A — Schema deltas found while planning

These are gaps between `architecture.md` §4.1 and what `edgecase.md` / `evals.md` require. All are P0 tasks.

### A.1 `exclusions` becomes a marking table, not a removal

**Problem.** S1-INV-1 reads `count(raw) == count(records) + count(exclusions)`, implying excluded records never enter `records`. But FR-1.5/1.6 require the exclusion log to be **browsable with its text**, and Appendix B requires prefilter-dropped records to be samplable into the gold set. Both are impossible if the rows are gone.

**Fix.** `records` retains every collected record. `exclusions.record_id` becomes a foreign key into `records`. The identity becomes:

```sql
count(records) == count(retained) + count(DISTINCT excluded.record_id)
```

`retained` is a view: records with no exclusion row. Analysis denominators use the view; the Data Bank and the gold sampler use the base table.

### A.2 Missing record-level flags

`edgecase.md` mandates three flags with nowhere to live:

| Flag | Required by | Add to |
|---|---|---|
| `secondhand` | EC-REL-4, EC-REL-5 — opinion about others, excluded from counterfactual and workaround analysis | `relevance` |
| `myntra_specific` | EC-REL-6 — claims resting mostly on non-Myntra records are marked per A-4 | `relevance` |
| `text_available` | EC-COL-14 — paywalled/image-only curated items. **Never quote what was not read** | `records` |

Downstream consequence: workaround and counterfactual analytics must filter `secondhand = 0`, and every insight must report the `myntra_specific` share of its supporting records.

### A.3 `gold` PK blocks the intra-rater test

**Problem.** `gold` has `record_id` as PRIMARY KEY. T-13 / EC-VAL-1 requires 20 records labelled **twice**, in separate sittings, to measure labeller drift. The PK makes the second label an overwrite.

**Fix.** `PRIMARY KEY (record_id, pass_no)` with `pass_no INTEGER NOT NULL DEFAULT 1`, plus `sitting_id` and `labelled_at`. Scoring uses `pass_no = 1`; T-13 compares pass 1 against pass 2 on the repeated subset. The labeller must not reveal that a record is a repeat.

### A.4 Long-record chunking has no representation

**Problem.** EC-COL-5 splits long records into chunks "sharing one `record_id`", but `record_id` is the PK of `records` and of `record_meta`.

**Fix.** Chunking happens **at classification time only** and is never persisted as rows in `records`. `classifications` gains `chunk_index INTEGER DEFAULT 0`; the PK becomes `(record_id, code, chunk_index, run_id)`. Codes are unioned to record level for all analysis; `chunk_index` exists so an `evidence_span` can be located in the right part of a long post.

### A.5 Prefilter decisions must be persisted

`prefilter` decisions are written as exclusion rows with `stage = 'prefilter'` **and** as a `prefilter_score` column, so S2-MET-6 can ask "would the prefilter have kept this gold-relevant record?" without re-running it.

---

## Appendix B — The gold sampling frame (a correction to arch §6.6)

**The problem.** `architecture.md` §6.6 draws the gold set from *pilot output* — records that passed the prefilter and were classified. But `evals.md` asks that same gold set to measure:

- **T-5, prefilter recall ≥ 95%** — of relevant records, how many did the prefilter keep?
- **T-2, relevance recall ≥ 85%** — of relevant records, how many did the LLM mark relevant?

Both are **recall** metrics. Recall requires the sample to contain records the filter *rejected*. A gold set drawn only from survivors makes prefilter recall trivially 100% and relevance recall unmeasurable — while producing a number that looks like a passing grade. This is exactly the silent-failure class `edgecase.md` §10 is built to catch, sitting inside the instrument meant to catch it.

**The fix — sample from the raw pilot corpus, stratified across the decision boundary:**

| Stratum | n | Purpose |
|---|---|---|
| Classified, high confidence | 40 | Baseline agreement (T-3, T-4) |
| Classified, **low confidence** | 30 | Where the classifier is weakest — over-sampled deliberately |
| **Z-99** | 20 | Is the residual real, or a codebook hole? (AC-11) |
| **C1 / C8 assigned** | 20 | The named danger pair (T-7 / EC-CLS-12) |
| **LLM-relevant = 0** (passed prefilter, judged irrelevant) | 25 | **Makes T-2 relevance recall measurable** |
| **Prefilter-rejected** | 25 | **Makes T-5 prefilter recall measurable** |
| Repeated items (drawn from the above, second sitting) | 20 | T-13 intra-rater agreement |
| **Total distinct** | **160** | Inside the 150–200 band |

Stratification is also spread across all four sources so that per-source relevance behaviour is visible (EC-VAL-4 — pilot vs full-corpus distribution drift is re-checked after the full run).

**Labelling protocol:** two sittings, 20 records silently repeated in the second (EC-VAL-1). Where the model looks right and the human looks wrong, the gold label may be amended — **recorded in `gold.notes` with the reason, never silently** (EC-VAL-5). Gold is one person's judgement, not ground truth.

---

## Appendix C — Descope ladder

If the schedule slips, cut in this order. The first block is load-bearing: each item guards a failure that would otherwise reach the deck **looking correct**.

**Never cut, in any circumstance:**
S2-INV-2 (evidence spans) · S1-PROBE-1 (consensus preservation) · S2-MET-6 (prefilter recall) · S4-INV-2 (numeric verification) · §8.3 injection probes · S4-OPS-3 (spend cap) · S2-MET-1/4 (gold metrics — AC-9 rests entirely on them) · Appendix B sampling frame (without it, two of the above are unmeasurable)

**Reduce rather than cut:**

| Item | Reduced form |
|---|---|
| Corpus size | 2,000 → 1,200 relevant. Report thinner tails honestly; the minimum-n gate already handles it |
| Golden question set | 60 → 30, **every category still represented** |
| Gold set | 160 → 120, keeping all seven strata proportionally |
| Curated research | 20 items → 8, still 100% URL-verified |

**Cut first if forced:**
S4-LLM-1 (advisory anyway) · S2-CLU-3 · S3-MET-2 (report a single ranking, state robustness untested) · multilingual golden category · S2-HUM-3

**Cut last, and only with the consequence written into the deck:**
Track B clustering. It costs under a dollar and it is the *only* protection against R-9 codebook blindness. Cutting it means AC-6 novelty has nowhere to come from, and the honest report becomes "we could not have discovered a barrier outside our own hypothesis list."
