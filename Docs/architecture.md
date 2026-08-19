# Architecture — AI-Powered Discovery Engine (Myntra Wishlist Conversion)

**Document status:** v1 — technical design derived from `problemstatement.md`
**Companion docs:** `edgecase.md`, `evals.md` (written) · `implementationplan.md` (to follow)
**Host:** Streamlit (Community Cloud)
**Models:** OpenAI frontier tier throughout (§9)
**Embeddings:** OpenAI `text-embedding-3-small` — offline only
**Scope:** how the engine is built. What it must do, and why, lives in `problemstatement.md` — every requirement ID referenced here (FR-*, NFR-*, AC-*, R-*, C-*) is defined there.

---

## 1. Purpose

`problemstatement.md` closed with ten open questions for architecture. This document answers all of them:

| # | Question | Answer | §  |
|---|---|---|---|
| 1 | Corpus size target | 2,000 relevant records; yield rate measured on a pilot | 5.2 |
| 2 | Collection mechanism | Four collectors — Play, App Store, Reddit API, YouTube API — plus agent-sourced curated research | 5.1 |
| 3 | Classification approach | Two-pass hierarchical classification on the frontier model + independent inductive clustering + reconciliation | 6 |
| 4 | Retrieval design for Q&A | Plan → 5 parallel retrieval channels → deterministic gate → contracted synthesis → code-level verification. No runtime vectors | 8 |
| 5 | Stack | Offline Python pipeline writing frozen artifacts; read-only Streamlit app; OpenAI models throughout | 2, 3 |
| 6 | Weighting scheme | Evidence-strength composite with user-adjustable weights and live sensitivity analysis | 7.2 |
| 7 | Ground-truth set | 150–200 stratified records, labelled in-app on **pilot** output before the full run | 6.6 |
| 8 | Codebook prompt strategy | Two-pass hierarchical — stage first, then codes within stage (≤14, not 33) | 6.2 |
| 9 | Blocking-code determination | Journey-rank minimum over assigned codes above a confidence floor | 7.1 |
| 10 | Segment inference confidence | Explicit threshold; below it the label is `unknown`, and `unknown` is reported not hidden | 6.3 |

---

## 2. System overview

The system splits along one hard line: **the pipeline computes, the app displays.**

```
┌─────────────────────────── OFFLINE (laptop) ────────────────────────────┐
│                                                                          │
│  COLLECT          CLEAN            CLASSIFY           CLUSTER            │
│  ┌────────┐      ┌────────┐      ┌──────────┐      ┌──────────┐        │
│  │ Play   │      │ dedupe │      │ prefilter│      │ embed    │        │
│  │ AppSt  │─────▶│ lang   │─────▶│ relevance│─────▶│ UMAP     │        │
│  │ Reddit │      │ PII    │      │ stage    │      │ HDBSCAN  │        │
│  │ YouTube│      │ normal │      │ codes    │      │ label    │        │
│  │ Curated│      └────────┘      └──────────┘      └──────────┘        │
│  └────────┘                            │                 │              │
│                                        ▼                 ▼              │
│                                   ┌──────────────────────────┐          │
│                                   │  RECONCILE + ANALYSE     │          │
│                                   │  lift · blocking · JS    │          │
│                                   │  counterfactual · x-tabs │          │
│                                   └──────────────────────────┘          │
│                                        │                                 │
│                                        ▼                                 │
│                            ┌───────────────────────┐                    │
│                            │  data/corpus.db       │  ◀── frozen        │
│                            │  data/artifacts/*.pq  │      artifacts     │
│                            └───────────────────────┘                    │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │  git commit
                                   ▼
┌─────────────────────────── ONLINE (Streamlit Cloud) ─────────────────────┐
│   1_Data_Bank    2_Analysis    3_Insights    4_Ask    9_Label            │
│   read-only      read-only     read-only     ▲ only live LLM calls       │
└──────────────────────────────────────────────────────────────────────────┘
```

### Why this split

| Reason | Detail |
|---|---|
| **Streamlit cannot do the work** | Community Cloud has ~1GB RAM, no persistent disk, and sleeps on inactivity. Multi-hour scrapes and batch classification cannot live there. |
| **Reruns would re-bill** | Streamlit re-executes the script top-to-bottom on *every* widget interaction. An in-app classification call would re-charge on each click. |
| **NFR-3 reproducibility** | Frozen artifacts mean the numbers on a slide do not move between page loads or between sessions. |
| **NFR-1 traceability** | Every displayed figure is a stored row with a `run_id`, not a value computed live from a prompt. |

The chatbot is the sole exception: it makes a small number of LLM calls per user question, against precomputed data.

### Consequence of the no-runtime-vectors decision

Embeddings are needed only for offline prefiltering and clustering. `embeddings.npy` **never ships to Streamlit**. The deployed app has no torch, no sentence-transformers, no ONNX runtime, no vector store — which is what keeps it inside the 1GB budget with room to spare.

Because embeddings come from the OpenAI API rather than a local model, the *pipeline* has no heavy ML dependency either — no torch anywhere in the project. `umap-learn` and `hdbscan` are the only non-trivial pipeline installs.

---

## 3. Repository layout

```
myntra-discovery-engine/
├── app/                            # Streamlit — READ ONLY
│   ├── Home.py                     # what this is, how it works (the 1-slider, AC-8)
│   ├── pages/
│   │   ├── 1_Data_Bank.py
│   │   ├── 2_Analysis.py
│   │   ├── 3_Insights.py
│   │   ├── 4_Ask.py
│   │   └── 9_Label.py              # gold-set labelling (internal, password-gated)
│   └── lib/
│       ├── db.py                   # cached read-only connection
│       ├── charts.py               # colour-blind-safe palette, n always shown
│       ├── retrieval.py            # BM25 + code filter + whitelisted SQL
│       └── citations.py            # record_id → Data Bank deep link
├── pipeline/
│   ├── collect/
│   │   ├── play_store.py
│   │   ├── app_store.py
│   │   ├── reddit.py
│   │   ├── youtube.py
│   │   └── curated.py              # agent-sourced research, same schema
│   ├── clean/
│   │   ├── dedupe.py
│   │   ├── language.py
│   │   └── scrub.py
│   ├── classify/
│   │   ├── prefilter.py            # free lexicon + embedding gate
│   │   ├── relevance.py            # LLM pass 0
│   │   ├── stage.py                # LLM pass 1
│   │   ├── codes.py                # LLM pass 2
│   │   └── batch.py                # Batches API driver, caching, retries
│   ├── cluster/
│   │   ├── embed.py                # text-embedding-3-small, offline only
│   │   └── discover.py             # UMAP + HDBSCAN + LLM cluster labelling
│   ├── analyse/
│   │   ├── reconcile.py            # cluster × code diagnostics
│   │   ├── derived.py              # lift, blocking, JS divergence, indices
│   │   └── crosstabs.py            # materialises analysis_* tables
│   ├── synthesise/
│   │   ├── insights.py
│   │   ├── hypotheses.py
│   │   └── artefacts.py            # interview guide, survey, canvas
│   └── validate/
│       └── goldset.py              # sampling + scoring against human labels
├── codebook/
│   ├── codebook_v1.yaml            # the 33 codes — pre-registered, frozen
│   └── segments_v1.yaml
├── data/
│   ├── corpus.db                   # SQLite — committed
│   ├── artifacts/*.parquet         # large analysis tables
│   └── embeddings.npy              # LOCAL ONLY, gitignored
├── prompts/                        # versioned prompt templates
├── Docs/
│   ├── Myntra Project Description.pdf          # the assignment
│   ├── Myntra Project's Current solution .pdf  # the original blueprint
│   ├── problemstatement.md
│   ├── architecture.md
│   ├── edgecase.md
│   ├── evals.md
│   └── implementationplan.md
├── requirements.txt                # app deps only — kept minimal
├── requirements-pipeline.txt       # heavy deps, never installed on Cloud
└── .streamlit/secrets.toml         # OPENAI_API_KEY (chatbot only)
```

**Two requirements files is deliberate.** `requirements.txt` is what Streamlit Cloud installs: `streamlit`, `pandas`, `plotly`, `rank-bm25`, `openai`. The pipeline's extra dependencies (`umap-learn`, `hdbscan`, `datasketch`, `praw`, scrapers) live in `requirements-pipeline.txt` and never reach the deployed app.

---

## 4. Data model

SQLite (`data/corpus.db`) — single file, zero-config, queryable, git-committable, and directly readable by Streamlit. Large derived tables spill to Parquet.

### 4.1 Core tables

```sql
-- Raw collected material. Immutable once written.
CREATE TABLE records (
  record_id     TEXT PRIMARY KEY,      -- sha1(source || native_id)
  source        TEXT NOT NULL,         -- play|appstore|reddit|youtube|curated
  source_url    TEXT NOT NULL,         -- permalink — NFR-1, no record without one
  native_id     TEXT,
  author_hash   TEXT,                  -- salted hash, never the handle (NFR-7)
  created_at    TEXT,                  -- ISO8601, NULL if source gives none
  text_raw      TEXT NOT NULL,
  text_clean    TEXT NOT NULL,
  lang          TEXT,                  -- en|hi|hi-Latn|mixed|other
  rating        INTEGER,               -- 1-5 where applicable, else NULL
  thread_context TEXT,                 -- parent post title / video title
  collect_query TEXT,                  -- what search surfaced it — bias auditing
  collected_at  TEXT NOT NULL,
  ingest_run_id TEXT NOT NULL
);

-- What was thrown away and why. A finding in its own right (FR-1.6).
CREATE TABLE exclusions (
  record_id  TEXT, source TEXT, stage TEXT,   -- dedupe|length|lang|prefilter|relevance
  reason     TEXT, detail TEXT, run_id TEXT
);

-- LLM pass 0.
CREATE TABLE relevance (
  record_id   TEXT PRIMARY KEY REFERENCES records(record_id),
  is_relevant INTEGER NOT NULL,
  reason      TEXT NOT NULL,
  confidence  REAL NOT NULL,
  run_id      TEXT NOT NULL
);

-- LLM pass 2. One row per (record, code) — multi-label by construction (FR-2.3).
CREATE TABLE classifications (
  record_id     TEXT REFERENCES records(record_id),
  code          TEXT NOT NULL,         -- A1.1 … D4, or Z-99
  confidence    REAL NOT NULL,
  evidence_span TEXT NOT NULL,         -- exact quote from text_clean (NFR-1)
  is_blocking   INTEGER NOT NULL DEFAULT 0,
  run_id        TEXT NOT NULL,
  PRIMARY KEY (record_id, code, run_id)
);

-- Record-level attributes (FR-5.3).
CREATE TABLE record_meta (
  record_id        TEXT PRIMARY KEY REFERENCES records(record_id),
  stages           TEXT,               -- JSON array, e.g. ["C"] or ["B","C"]
  blocking_code    TEXT,
  blocking_phase   TEXT,               -- eliminator|confidence|trigger
  outcome          TEXT,               -- exit|defer|na
  segment          TEXT,               -- S1|S2|S3|unknown
  segment_conf     REAL,
  workaround       INTEGER,            -- 0/1
  workaround_text  TEXT,
  workaround_effort INTEGER,           -- 1-3
  counterfactual   INTEGER,            -- "I'd have bought it if…"
  counterfactual_text TEXT,
  intensity        INTEGER,            -- 1-5
  run_id           TEXT NOT NULL
);

-- Inductive track — deliberately blind to the codebook.
CREATE TABLE clusters (
  record_id TEXT REFERENCES records(record_id),
  cluster_id INTEGER, probability REAL, run_id TEXT
);
CREATE TABLE cluster_labels (
  cluster_id INTEGER, label TEXT, description TEXT,
  size INTEGER, exemplar_ids TEXT, run_id TEXT
);

-- Human ground truth (AC-9). Written by the in-app labeller.
CREATE TABLE gold (
  record_id    TEXT PRIMARY KEY REFERENCES records(record_id),
  is_relevant  INTEGER NOT NULL,
  codes        TEXT NOT NULL,          -- JSON array
  segment      TEXT,
  labelled_at  TEXT NOT NULL,
  notes        TEXT
);

-- Provenance for every pipeline execution (NFR-4).
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, stage TEXT, started_at TEXT, finished_at TEXT,
  model TEXT, prompt_version TEXT, codebook_version TEXT,
  n_input INTEGER, n_output INTEGER,
  input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER,
  cost_usd REAL, params_json TEXT
);
```

### 4.2 Materialised analysis tables

Precomputed by `pipeline/analyse/crosstabs.py`, read directly by the app and by the chatbot's quantitative path. Every one carries `n` and `run_id`.

`analysis_code_prevalence` · `analysis_segment_code` · `analysis_cooccurrence` (with lift and PMI) · `analysis_source_code` · `analysis_stage_outcome` · `analysis_workaround` · `analysis_counterfactuals` · `analysis_cluster_code` · `analysis_evidence_strength` · `analysis_opportunity`

**Design rule:** the app performs no aggregation over raw records. Everything it displays is a `SELECT` from a materialised table. This guarantees the chatbot and the charts cannot disagree — they read the same rows.

### 4.3 The codebook as data, not prose

`codebook/codebook_v1.yaml` is the single source of truth, consumed by the classifier prompt, the app's codebook page, the labelling UI, and the analytics:

```yaml
version: v1
frozen_at: "<date pipeline first runs>"
codes:
  - id: C1
    stage: C
    name: Fit & size uncertainty
    phase: confidence
    outcome: defer
    journey_rank: 5
    solvable_without_money: yes
    question: "Which size, when every brand runs different?"
    blueprint_refs: [H6, H11, DH5]
    workarounds: [ordering two sizes, checking a garment they own, abandoning]
    boundary_note: >
      Doubt about WHICH size to pick. If the size simply is not purchasable,
      that is C8, not C1 — different phase, different solve.
```

`boundary_note` exists specifically to fight the C1/C8 confusion class (§6.6). Frozen before scoring per FR-5.6; a version bump forces full re-classification.

---

## 5. Stage 1 — Data Bank

**Discharges:** FR-1.1 … FR-1.6, A-1
**Ships:** Data Bank browser, corpus composition dashboard, exclusion log

### 5.1 Collectors

| Source | Library | Target | Notes |
|---|---|---|---|
| Play Store | `google-play-scraper` | `com.myntra.android`, `country=in` | Highest volume. Low relevance yield — mostly delivery/refund |
| App Store | `app-store-scraper` | Myntra iOS, `country=in` | Lower volume, similar skew |
| Reddit | `praw` | r/IndianFashionAddicts, r/IndianFashion, r/TwoXIndia, r/india, r/DesiFashion + full-text search | Best source for *reasoning*. Long-form "why I didn't buy" |
| YouTube | `google-api-python-client` | `commentThreads` on haul/unboxing/review videos | Uniquely captures C14 (off-platform verification) |
| Curated | agent-sourced | Research on Indian online fashion behaviour, cart-abandonment studies, industry reports | Fills the Stage A blind spot that complaint sources structurally miss |

All collectors emit the same `records` schema. `collect_query` is stored so we can later audit whether a theme's prevalence is an artefact of the search terms used to find it.

**Collection is over-generous by design.** At a target of 2,000 *relevant* records and an unknown yield rate, we collect wide and let the filters cut down. Everything cut is logged (FR-1.6).

### 5.2 The pilot — resolving A-1

Assumption A-1 (enough relevant public feedback exists) is currently unverified and gates the whole project. The pilot runs first:

1. Collect ~1,500 raw records, spread across all four sources
2. Run prefilter + LLM relevance
3. Report **yield rate per source** — relevant ÷ collected
4. Classify the survivors, so there is labelled output to draw the gold set from

The yield rate sizes the full collection run. If Play Store yields 3% and Reddit yields 40%, collection effort reweights accordingly — at a 2,000-record target, the difference decides whether the corpus is Reddit-led or app-store-led, which in turn drives the source-bias caveats in `problemstatement.md` §8.

Deliberately spread thin across sources rather than deep in one: the purpose is measuring *relative* yield, and a pilot drawn mostly from Play Store would measure the wrong thing.

The pilot's classified output is what the gold set is drawn from (§6.6), so this single step resolves A-1, sizes Stage 1, and seeds validation.

### 5.3 Cleaning

| Step | Method | Logged as |
|---|---|---|
| Exact dedupe | sha1 of normalised text | `dedupe/exact` |
| Near dedupe | MinHash LSH (`datasketch`), Jaccard > 0.85 | `dedupe/near` |
| Length floor | < 15 chars after normalisation | `length` |
| Language | `fasttext` langid; Latin-script + Hindi lexicon markers → `hi-Latn` | `lang` |
| PII scrub | regex: email, phone, order IDs; author → salted hash | — |
| Normalise | collapse whitespace, strip emoji-only content, preserve `text_raw` verbatim | — |

Hinglish is **kept, never translated**. Translation would destroy the verbatim evidence that NFR-1 depends on. The classifier reads code-mixed text directly, and `text-embedding-3-small` embeds it directly.

### 5.4 Streamlit page — `1_Data_Bank.py`

- Filter by source, date, language, rating, relevance, code, segment
- Full-text search over `text_clean`
- Record detail: verbatim text, provenance link, all assigned codes with evidence spans
- **Corpus composition dashboard** — records per source, per month, language mix, relevance yield per source
- **Exclusion log** — what was dropped and why, browsable

The composition dashboard is not decoration. It is the evidence base for the source-bias caveats in `problemstatement.md` §8, and a mentor asking "what's in your corpus?" gets an answer with numbers.

### 5.5 Exit gate

Pilot yield measured and reported · 2,000 relevant records collected · every record has a resolvable `source_url` · exclusion log populated · **deployed to Streamlit** · AC-1 (partial), AC-2 satisfied for raw records.

---

## 6. Stage 2 — Analysis

**Discharges:** FR-2.1 … FR-2.6, FR-5.1 … FR-5.7, AC-9, AC-10, AC-11
**Ships:** analysis dashboard, all cross-tabs, drill-through to records, validation report

Three tracks. Track A quantifies, Track B discovers, Track C finds what neither sees alone.

### 6.1 Pass 0 — prefilter, then relevance

Cost control. LLM-scoring every raw record is the single largest expense in the project, and most of them are obviously irrelevant.

```
raw (~8K) ──▶ lexicon gate ──┐
                             ├──▶ union (~3K) ──▶ LLM relevance ──▶ relevant (2K)
          ──▶ embedding gate ─┘
```

- **Lexicon gate (free):** wishlist / saved / save for later / add to bag / "thinking of buying" / "planning to buy" / "still haven't bought"
- **Embedding gate (free, offline):** cosine similarity against ~50 hand-written exemplar sentences describing save-then-hesitate behaviour; top-N by similarity
- **Union, not intersection** — recall matters more than precision here; the LLM pass is the precision step

The **LLM relevance pass** is deliberately narrow. Relevant = bears on the decision between *saving/intending* and *purchasing*. Excluded: delivery delays, refund processing, app crashes, customer service, post-purchase quality complaints.

One critical carve-out: a past bad experience **cited as a reason for present hesitation** is relevant (that is C7/H8). "My last order came in the wrong size and I'm wary now" is in. "My order was late" is out. This distinction is where a naive filter fails, and it is explicitly tested in the gold set.

### 6.2 Track A — deductive classification (two-pass hierarchical)

Answers open question #8. Thirty-three codes in a single prompt degrades accuracy — the model spreads attention thin and confuses adjacent codes. Split it:

**Pass 1 — stage assignment.** Input: record. Output: one or more of `A|B|C|D`, or `Z-99`. Small prompt, cheap, high accuracy.

**Pass 2 — codes within assigned stage(s) only.** A record assigned to C sees 14 codes, not 33. The prompt carries the **full `boundary_note` text for every candidate code** — affordable precisely because the set is narrower, and load-bearing because the boundaries are where classification fails.

Pass 2 output per record, via **structured outputs** (JSON schema, `strict: true`) so the schema is enforced rather than hoped for:

```json
{
  "codes": [
    {"code": "C1", "confidence": 0.86,
     "evidence_span": "never know my size in this brand",
     "reasoning": "Doubt about which size to choose, not about availability — C1 not C8"}
  ],
  "blocking_code": "C1",
  "outcome": "defer",
  "segment": {"label": "S1", "confidence": 0.72, "signal": "need it by Saturday"},
  "workaround": {"present": true, "text": "ordered two sizes", "effort": 2},
  "counterfactual": {"present": true, "text": "would have bought if I knew the fit"},
  "intensity": 4
}
```

**The `reasoning` field is retained deliberately.** It is the largest single output-token cost in the pipeline, and it earns it three times over: it is the auditable rationale NFR-4 requires; it is what makes the gold-set confusion analysis show *why* a code was misassigned rather than merely *that* it was; and writing the justification measurably improves boundary discrimination on exactly the C1/C8-style distinctions the project turns on.

**Full frontier model on every pass.** No tier splitting, no confidence-gated escalation, no embedding shortlist of the codebook. Every record is classified by the best available model against the complete stage codebook. The analysis is the project's validity — the entire wishlist→purchase conclusion rests on these labels being right, and the total cost of doing it properly (§9) is small enough that trading accuracy for it would be a poor bargain.

**Execution:** OpenAI **Batch API** (50% discount, 24h window — irrelevant to an offline pipeline that runs a handful of times) with the codebook prefix stable across every record, so **automatic prompt caching** applies to the shared portion. Both discounts compose, and neither costs any accuracy.

### 6.3 Segment inference

Answers open question #10. Segment is assigned only above a confidence threshold (initial: 0.6); below it, `unknown`.

`unknown` is expected to be the **majority** — public text rarely states why someone saved. Per `problemstatement.md` §5.8, segment-conditional results are computed only over the labelled subset, and coverage is displayed beside every segment chart. The app never renders a segment breakdown without its coverage figure.

### 6.4 Track B — inductive discovery

Runs on the same relevant set, **blind to the codebook**. This is the check against R-9 (codebook blindness).

```
text-embedding-3-small (1536-d, offline) → UMAP (n_neighbors=15, min_dist=0.0, n_components=10)
                         → HDBSCAN (min_cluster_size = max(15, n/200))
                         → per cluster: 15 representative records (centroid-near + diverse)
                         → LLM labels: name, description, what unites them
```

The Z-99 residual is clustered **separately** — that is the FR-5.4 mechanism for proposing new codes.

### 6.5 Track C — reconciliation and derived analytics

This is where non-obvious patterns come from. Neither track produces them alone.

**Cluster × code reconciliation.** Build the contingency table, then compute entropy in both directions:

| Signal | Meaning | Action |
|---|---|---|
| One code → many clusters (high entropy) | Code is **too coarse** — it hides distinct sub-problems with different solves | Candidate split |
| One cluster → many codes (high entropy) | Code **boundary is wrong** — the model can't separate them | Sharpen `boundary_note`, re-run |
| Cluster with no dominant code | **New territory** | Z-99 → candidate new code (feeds AC-6) |

**Derived analytics:**

| Analysis | Method | What it surfaces |
|---|---|---|
| **Co-occurrence lift** | `lift(i,j) = P(i,j)/(P(i)·P(j))`, PMI = log₂(lift), min support guard | Surprising pairings, not frequent ones. C1×C7 lift of 3.2 means fit doubt and return friction are one compound problem, not two independent ones |
| **Blocking code** | Minimum `journey_rank` among assigned codes above the confidence floor | An Eliminator failure makes every downstream Confidence solve worthless. Ranking by raw prevalence hides this entirely |
| **Counterfactual mining** | Filter `counterfactual = 1`, cluster the texts | Self-reported blocking barriers — "I'd have bought it if…" is the highest-signal sentence type in the corpus |
| **Workaround intensity** | `mean(effort) × share_with_workaround` per code | Effort spent proves unmet need better than complaint volume. A quiet barrier people work around hard beats a loud one they merely grumble about |
| **Source divergence** | Jensen–Shannon divergence, per-source code distribution vs pooled | Separates real signal from platform demographics. High JS = the code may be an artefact of who posts there |
| **Segment × code** | Cross-tab with coverage | The artefact that selects the target segment (AC-12) |
| **Intensity × prevalence** | 2×2 map | High-intensity/low-prevalence codes are invisible to volume ranking but may matter most |
| **Evidence strength** | Weighted composite: prevalence, source diversity, counterfactual rate, workaround rate, mean confidence, recency | Downgrades a code carried by one source; upgrades one corroborated across four |

### 6.6 Validation — the gold set

**Order matters: label the pilot, fix the prompt, then spend the full budget.** Finding a broken code definition after classifying 10,000 records means paying twice.

1. Stratified sample of 150–200 from **pilot** output — across sources, predicted stages, plus deliberate over-sampling of low-confidence records and Z-99
2. User labels in `9_Label.py`: relevance, codes, segment — clicking through records against the codebook, not spreadsheet work
3. `pipeline/validate/goldset.py` scores:
   - relevance accuracy / precision / recall — **AC-9 target ≥80%**
   - per-code agreement + Cohen's κ — **AC-9 target ≥70%**
   - **code confusion matrix** — which pairs get conflated
4. Below threshold → sharpen the offending `boundary_note`, bump prompt version, re-run pilot, re-score

The confusion matrix is the actionable output. The C1/C8 pair (fit uncertainty vs size unavailable) is the known danger: they read similarly and have opposite solves — one is a solvable confidence problem, the other is supply-side and fails the C-2 constraint. Confusing them means building the wrong thing while the data appears to agree.

### 6.7 Streamlit page — `2_Analysis.py`

Every chart: colour-blind-safe palette, `n` displayed, click-through to supporting records (AC-2). No chart renders a percentage without its denominator.

### 6.8 Exit gate

Gold set labelled, AC-9 thresholds met · Z-99 < 15% or codebook revised and re-run (AC-11) · all 33 codes scored including zero-count ones (AC-10) · all cross-tabs materialised · **deployed to Streamlit**.

---

## 7. Stage 3 — Insights & Hypotheses

**Discharges:** FR-3.1 … FR-3.5, AC-5, AC-6, AC-7, AC-12
**Ships:** ranked opportunities, segment recommendation, generated research artefacts

### 7.1 Insight generation

Insight = a quantified statement with evidence. Hypothesis = a causal claim with a falsifier.

Each hypothesis record carries: supporting count, representative verbatims, source diversity, confidence, **contradicting evidence**, and **what would disprove it** (AC-7). Generated by the frontier model over the *analysis tables*, not raw records — so every claim is anchored to a computed number.

### 7.2 Opportunity scoring, with the weights exposed

```
opportunity = w₁·prevalence + w₂·intensity + w₃·defer_share
            + w₄·solvable_without_money + w₅·evidence_strength + w₆·segment_fit
```

Weights are **sliders in the app**. This is a deliberate design choice, not a convenience: a single hard-coded ranking invites "why those weights?" A live sensitivity panel lets an evaluator move them and see whether the top opportunity is robust or an artefact of the scoring. A ranking that survives the sliders is a much stronger claim than one asserted.

C9 (intent never live) and S3 (bookmarkers) are **sized and then excluded** from the addressable opportunity, per AC-12 — leaving them in the denominator inflates the opportunity and is the easiest way to produce a wrong answer that survives casual review.

### 7.3 Stage A bias correction — the "what would you need to believe" panel

`problemstatement.md` §8 establishes that the corpus structurally under-detects Stage A: forgetting produces no complaint. A low A-count is therefore not evidence that A is small.

Rather than silently accepting the ranking, the app shows the inversion threshold: **how far Stage A would have to be under-reported for it to overtake the leading stage.** If the answer is "3× under-reporting," that is plausible for a silent barrier and the conclusion is fragile. If it is "40×," the ranking is safe.

This turns an acknowledged weakness into a quantified sensitivity — the honest handling of proxy data that §8 demands.

### 7.4 Generated artefacts (FR-3.4)

Interview guide for the 5–6 interviews (Part 3), survey instrument, and problem-framing canvas — each pre-populated with the top hypotheses and their falsifiers, so primary research tests what the corpus actually raised.

### 7.5 Exit gate

Ranked stage comparison with counts, confidence, and limitations (AC-5) · ≥1 insight outside H1–H15/DH1–DH13 (AC-6) · every hypothesis has a falsifier (AC-7) · segment recommendation justified against the matrix (AC-12) · **deployed**.

---

## 8. Stage 4 — The research analyst (RAG chatbot)

**Discharges:** FR-4.1 … FR-4.5, AC-3, AC-4
**Ships:** grounded Q&A over the corpus, the analysis, and the hypotheses

### 8.1 Design goal — an analyst, not a search box

The failure mode of ordinary RAG is that it behaves like a search engine wearing a conversational costume: it embeds the question, pulls the five nearest chunks, and asks a model to write something plausible over them. That produces fluent text with no denominator, no dissent, no stated confidence, and numbers the model invented because a chunk happened to mention "many users."

This chatbot is built to behave the way a research analyst does when asked a question:

| A researcher… | Mechanism here |
|---|---|
| Works out what is *really* being asked, including the unasked sub-questions | §8.3 question analysis |
| Decides what evidence *would* answer it, before looking | §8.3 evidence plan |
| Gathers from several angles, not one | §8.4 five retrieval channels |
| Actively looks for evidence *against* the emerging answer | §8.4 channel 3 |
| Quantifies, with a denominator | §8.4 channel 1 — real SQL, never estimated |
| Quotes primary sources verbatim | §8.4 channel 2 — exact spans |
| Separates what the data says from what they infer | §8.6 answer contract |
| States confidence and limitations, unprompted | §8.6 mandatory sections |
| Says "I can't answer that from this data" | §8.7 scope gate |

### 8.2 The loop

```
question
   │
   ▼
┌──────────────────────────────────────────────┐
│ 1. ANALYSE   what is being asked, really     │  1 LLM call
│              → intent, entities, sub-questions│
│              → evidence plan                  │
│              → answerability verdict          │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│ 2. RETRIEVE  five parallel channels           │  0 LLM calls
│              facts · verbatim · disconfirming │  (SQL + BM25, local)
│              method · external                │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│ 3. GATE      does retrieval satisfy the plan? │  0 LLM calls
│              full / partial / none            │  (deterministic)
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│ 4. SYNTHESISE answer under the contract       │  1 LLM call
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│ 5. VERIFY    every number and quote checked   │  0 LLM calls
│              against retrieved data           │  (string/regex)
└──────────────────────────────────────────────┘
```

Two LLM calls per question. Steps 2, 3 and 5 are deterministic code — which is what makes the guarantees in §8.8 guarantees rather than instructions.

### 8.3 Step 1 — understanding the essence of the question

This is the step that separates the engine from keyword search. The question is not embedded and matched; it is **read and decomposed** into a structured plan.

```json
{
  "intent": "comparative",
  "restated": "Is fit uncertainty a larger barrier than price uncertainty at the item-decision stage?",
  "sub_questions": [
    "What share of save-decision discussion does C1 account for?",
    "What share does C6 account for?",
    "Is the gap larger than the noise given the sample sizes?",
    "Does the ordering hold across sources, or is it one platform's artefact?",
    "Does it hold within segments?"
  ],
  "entities": {"codes": ["C1","C6"], "stages": ["C"], "segments": null, "sources": null},
  "evidence_needed": ["prevalence+n for both", "source breakdown", "verbatims for both",
                      "segment split", "known biases for these codes"],
  "answerable": "likely",
  "quantitative": true
}
```

Three things this buys:

**Restatement.** The model commits to an interpretation before answering. Displayed to the user, so a misread question is visible rather than silently answered.

**Sub-questions are where the research posture lives.** A user asking "is fit bigger than price?" wants a comparison — but a researcher knows the answer is worthless without sample sizes, source robustness, and segment variation. The decomposition adds those unasked questions automatically, so the answer arrives complete rather than requiring five follow-ups.

**Answerability is assessed before retrieval, not after.** The plan states what evidence *would* settle the question. Step 3 compares that against what was actually found. A model that has already committed to "I need prevalence for C1 and C6" cannot later pretend that two verbatims constitute an answer.

Intent types: `quantitative` · `qualitative` · `comparative` · `causal` · `exploratory` · `methodological` (how was this built) · `out_of_scope`.

### 8.4 Step 2 — five retrieval channels

All five run in parallel, locally, with no LLM involvement. Which fire is determined by the plan.

**Channel 1 — Structured facts (the numbers).**
Whitelisted, parameterised queries over `analysis_*`. The planner chooses *which* query and its arguments; it never writes SQL. This eliminates injection, hallucinated column names, and invented aggregates. Returns rows with `n`, denominator, and `run_id`.

> This is the channel that makes quantitative honesty possible. The model does not estimate "about a third" from reading passages — it receives `{code: C1, records: 1240, share: 0.31, denominator: 4002, n_sources: 4}` and must quote it.

**Channel 2 — Verbatim evidence.**
BM25 (`rank-bm25`) over `text_clean`, filtered to the codes named in the plan, returning `evidence_span` plus the full record and its `source_url`. Code-filtering is what makes this precise: the corpus is already labelled, so "show me fit-uncertainty quotes" is an exact filter, not a similarity guess.

**Channel 3 — Disconfirming evidence.**
Deliberately retrieves against the emerging answer: records coded to the *rival* code, records where the plan's code co-occurs with something that complicates it, and Z-99 records matching the question's keywords. If the answer is "fit dominates," this channel surfaces the price-dominant records so the answer must account for them.

> Almost no RAG system does this. It is the difference between a system that confirms and a system that investigates — and it is what stops the chatbot from becoming the confirmation-bias machine that R-1 warns about.

**Channel 4 — Method and limitations.**
For every code in play, pulls source mix, mean classifier confidence, gold-set agreement, and any registered bias flag (e.g. Stage A structural under-detection per `problemstatement.md` §8). This is what lets confidence and caveats be *derived* rather than performed.

**Channel 5 — External corroboration.**
BM25 over the curated research sub-corpus (`source = 'curated'`). Lets the answer say "this is consistent with published findings on Indian online fashion returns" — or, more valuably, flag where the corpus *disagrees* with published research.

### 8.5 Step 3 — the gate

Deterministic comparison of `evidence_needed` (from the plan) against what the channels returned, using minimum-n thresholds:

| Outcome | Condition | Route |
|---|---|---|
| **FULL** | All required evidence present, above minimum n | Answer |
| **PARTIAL** | Some present, some missing or below n | Answer the supported part, **name** the unsupported part |
| **NONE** | Nothing relevant, or question is out of scope | Refuse, state what is missing |

Because the gate is code comparing two lists, refusal is a **deterministic outcome, not a matter of prompt compliance**. This is what makes AC-4 testable — the same question always routes the same way, and `evals.md` can assert it.

### 8.6 Step 4 — the answer contract

The synthesis call receives the plan, all retrieved evidence, the gate verdict, and a required output structure:

| Section | Rule |
|---|---|
| **Answer** | 1–2 sentences, direct. No preamble |
| **Evidence** | Every number quoted from Channel 1 with its `n` and denominator. Never a bare percentage |
| **In users' words** | 2–4 verbatim quotes with source links |
| **Variation** | By segment and source where meaningful, with coverage stated |
| **Counter-evidence** | Channel 3 findings. Written even when they weaken the answer — *especially* then |
| **Confidence** | High / Medium / Low, with the reason (sample size, source diversity, classifier agreement) |
| **Limitations** | What this evidence cannot establish. Always present |

Two hard rules in the system prompt:

1. **Inference must be labelled.** Any sentence not directly supported by a retrieved artifact is prefixed `Interpretation:`. The boundary between data and reading of the data is never blurred.
2. **Proxy discipline.** Corpus share is share of *discussion*, never a drop-off rate. The prompt forbids phrasing that implies funnel measurement — enforcing `problemstatement.md` §8 at the point of generation, not just in the docs.

### 8.7 Worked examples

**"Why don't people buy things from their wishlist?"** — exploratory, broad
Plan decomposes into top barriers by prevalence, segment variation, and known blind spots. Channel 1 returns the ranked table; Channel 2 pulls verbatims for the top codes; Channel 4 attaches the Stage A caveat. Answer leads with the ranking *and* the caveat that silent barriers are structurally under-represented — because Channel 4 supplied that, not because the model remembered to be humble.

**"Is fit a bigger problem than price?"** — comparative, quantitative
Both prevalences with n, the source breakdown (does the ordering survive per-source?), the segment split, verbatims for each, and Channel 3's counter-evidence. If the gap is inside the noise, the answer says the data cannot separate them — an outcome the gate can force, because the plan asked whether the gap exceeds the sample noise.

**"What is Myntra's revenue?"** — out of scope
Step 1 marks `out_of_scope`; retrieval is skipped entirely; the refusal states the engine covers public feedback on save-to-purchase behaviour and holds no financial data. Zero cost beyond the planning call.

**"Do users trust influencer reviews?"** — partial, the interesting case
The plan needs evidence on influencer-specific trust. Channel 2 returns strong C4 (real-buyer evidence) and C14 (off-platform verification) material — users leaving for YouTube — but nothing separating *influencer* content from *ordinary buyer* content. Gate returns PARTIAL. The answer states what the corpus does support (users leave the platform to seek buyer evidence, n=…), explicitly names what it cannot (no basis to distinguish influencer trust specifically), and notes what would be needed. **This is the behaviour AC-4 exists to test**, and the case most systems fail by smoothing over the gap.

### 8.8 Anti-hallucination guarantees

Enforced in code at step 5, after generation:

| Guarantee | Enforcement |
|---|---|
| **No invented numbers** | Every numeral in the answer is regex-extracted and matched against Channel 1 results. Unmatched → answer rejected and regenerated |
| **No invented quotes** | Every quoted string must be an exact substring of a retrieved record. Verified by string match |
| **No uncited claims** | Every paragraph carries ≥1 citation or an `Interpretation:` prefix |
| **No answer without evidence** | Enforced upstream by the gate, not by prompt instruction |
| **Traceable to raw** | Citations render as deep links into the Data Bank (AC-2) |

The distinction that matters: these are **post-generation checks in Python**, not requests in a prompt. A model that ignores an instruction still gets caught.

### 8.9 Exit gate

All ten canonical questions answered with citations (AC-3) · out-of-scope refusal and partial-answer behaviour verified (AC-4) · verification layer rejects a deliberately hallucinated number in testing · **deployed to Streamlit**.

---

## 9. Cost & performance model

Full-depth analysis, frontier model on every pass, no tier splitting. Corpus target **2,000 relevant records** (~8K raw collected).

### 9.1 Token volumes

Costed in tokens rather than dollars, so the estimate survives whatever the exact model rates turn out to be.

| Pass | Records | Fresh in | Cached in | Out |
|---|---|---|---|---|
| Relevance | ~3,000 | 0.6M | — | 0.30M |
| Stage assignment | 2,000 | 0.5M | — | 0.16M |
| Code assignment (full stage codebook + `reasoning`) | 2,000 | 0.6M | ~4M | 1.10M |
| Cluster labelling | ~20 | 0.06M | — | 0.01M |
| Insight + hypothesis synthesis | one-off | 0.5M | — | 0.10M |
| **Total** | | **~2.3M** | **~4M** | **~1.67M** |

Embeddings (corpus + code definitions + exemplars): ~0.25M tokens, well under a cent.

Synthesis does not scale with corpus size — it reads the analysis tables, not the records.

### 9.2 Cost

| Mode | Estimate |
|---|---|
| **Batch API (50% off) — recommended** | **~$11–14** |
| Synchronous | ~$22–28 |

**Budget ~1.5× the batched figure.** The gold set will very likely force one prompt fix and a pilot re-run; a codebook version bump forces full re-classification (FR-5.6); and chatbot usage during testing and the demo adds a few dollars.

| Line | Amount |
|---|---|
| Pipeline, batched | ~$11–14 |
| Re-runs (prompt fix, codebook bump) | ~$5 |
| Chatbot testing + demo (~300 questions) | ~$1.50 |
| **Realistic all-in** | **~$18–22** |
| **+18% GST (India) + ~3% forex** | **≈ ₹1,900–2,400** |

**Output tokens are ~80% of the bill.** 1.67M output tokens dominate; all input, including 4M of cached codebook, stays under $3. Two consequences:

- **Batch API is the highest-value lever in the project** — a straight 50% cut costing nothing but a 24-hour turnaround on a pipeline that runs a handful of times. Always use it.
- Prompt caching is free and worth enabling, but moves the total by about a dollar. It is not where the money is.

**Billing:** OpenAI is the only paid vendor. Streamlit Community Cloud, Reddit API, YouTube Data API (within quota), Play/App Store scraping and GitHub are all free. OpenAI API credits are **prepaid and separate from any ChatGPT subscription**. Set a hard usage cap (Billing → Limits) at $30 before the first batch job so a runaway loop cannot overrun the budget.

> **Pricing caveat.** Order-of-magnitude estimates against OpenAI's frontier tier; exact model IDs and rates should be confirmed at build time. The `runs` table records actual tokens and cost per pass, so the pilot replaces every figure here with a measurement.

### 9.3 Scale sensitivity

Cost scales close to linearly with relevant-record count, since output tokens dominate and output is per-record.

| Corpus | Batched | All-in | Analytical consequence |
|---|---|---|---|
| **2,000 relevant** | **~$11–14** | **~$18–22** | Top codes solid; long tail under-evidenced. Segment × code sparse — see §9.4 |
| 5,000 relevant | ~$25–30 | ~$40–45 | ~150 records/code average. Defensible segment matrix |
| 10,000 relevant | ~$50–60 | ~$75–85 | Strong tails and rare-code coverage; collection time becomes the bottleneck |

The pilot (§5.2) measures the relevant-record yield rate before the number is fixed. Scaling up later is a re-run, not a redesign — nothing in the architecture assumes 2,000.

### 9.4 Known consequence of 2,000 — and how it is reported

At this scale the corpus will not spread evenly, and the architecture must state that rather than hide it.

Stage C should take roughly 60% (~1,200 records) across 14 codes. The leading three or four codes land at 200–300 each; the tail sits at 10–20. AC-10 will therefore render as a few solid bars beside a long row of near-zeros. **That is a reportable result** — a code with no evidence is a finding — but it must be labelled *under-evidenced*, not *absent*.

The sharper constraint is **segment × code**. Only ~40% of records are expected to carry a confident segment label (§6.3), so the matrix cross-tabulates ~800 records across 14 codes and 3 segments. Most cells will fall below a readable n.

Two mitigations, both already required elsewhere:

- **Minimum-n gate.** Codes and cells below a floor (n ≥ 30 for a ranked claim, n ≥ 15 to appear at all) are rendered greyed with the count shown, never as a confident bar. This is R-4 enforcement made visible.
- **Segment analysis degrades to stage level.** Where segment × code is too sparse, the segment recommendation for AC-12 rests on segment × *stage* — a 3 × 4 matrix over the same 800 records, which holds adequate n — with code-level detail reported as directional.

### 9.5 Runtime

Chatbot: 2 LLM calls plus local retrieval, roughly $0.005 per question — a 300-question evaluation session costs about $1.50. All page loads are SQLite reads served from `@st.cache_data`. The Batch API's 24-hour window applies only to the offline pipeline and never touches the deployed app.

## 10. Deployment

| Concern | Approach |
|---|---|
| Platform | Streamlit Community Cloud, from GitHub |
| Artifacts | `corpus.db` committed. 2K records ≈ 5–10MB — trivially inside limits. If it exceeds ~100MB, move to a GitHub Release asset fetched on boot under `@st.cache_resource` |
| Embeddings | **Not deployed.** `embeddings.npy` is gitignored; offline clustering only |
| Secrets | `OPENAI_API_KEY` only, for the chatbot |
| Caching | `@st.cache_resource` for the DB connection, `@st.cache_data` for dataframes — Streamlit reruns on every interaction, so uncached reads would re-hit disk constantly |
| Cold starts | The app sleeps on inactivity. Keep `requirements.txt` minimal so wake-up is fast — this is the practical payoff of the no-runtime-vectors decision |
| Labelling page | Password-gated via secrets; writes to a separate `gold` store, synced back to the pipeline |

---

## 11. Traceability matrix

| Requirement | Satisfied by |
|---|---|
| FR-1.1–1.6 | §5.1 collectors, §5.3 cleaning, `records` + `exclusions` |
| FR-2.1 | §6.1 prefilter + LLM relevance |
| FR-2.2 | §6.2 two-pass hierarchical classification |
| FR-2.3 | `classifications` — one row per (record, code) |
| FR-2.4 | §6.4 Track B, §6.5 reconciliation |
| FR-2.5 | §6.5 derived analytics |
| FR-2.6 | §6.7 charts — colour-blind-safe, n always shown |
| FR-3.1–3.5 | §7.1 insights, §7.2 scoring, §7.3 bias correction |
| FR-4.1–4.5 | §8.3 question analysis, §8.4 five channels, §8.5 gate, §8.6 answer contract, §8.8 verification |
| FR-5.1–5.7 | §6.2, §6.3, `codebook_v1.yaml`, §6.5, §6.6 |
| NFR-1 traceability | `source_url` + `evidence_span` mandatory; deep-link citations |
| NFR-2 honesty | §8.2 scope gate; `unknown` as first-class label |
| NFR-3 reproducibility | Frozen artifacts; `runs` provenance; versioned codebook |
| NFR-4 auditability | `runs` table; versioned prompts; exclusion log |
| NFR-5 latency | Precomputed tables; one LLM call per question |
| NFR-6 cost | Prefilter, Batches API, prompt caching |
| NFR-7 ethics | Salted author hashes, PII scrub, public sources only |
| NFR-8 deployability | §10 |
| AC-1–AC-12 | Stage exit gates §5.5, §6.8, §7.5, §8.4 |

---

## 12. Risks to the architecture

Distinct from the product risks in `problemstatement.md` §11.

| # | Risk | Mitigation |
|---|---|---|
| AR-1 | Scrapers break (ToS, rate limits, API changes) | Four independent sources; snapshot the corpus early; degrade to smaller-but-cited over larger-but-fragile |
| AR-2 | `corpus.db` outgrows GitHub limits | Parquet spill for large tables; Release-asset fallback with boot-time fetch |
| AR-3 | Prompt cache misses (codebook edits mid-run) | Codebook frozen per FR-5.6; version bump forces a clean full re-run, never a partial one |
| AR-4 | Batch job partial failure | `run_id` checkpointing; resume by diffing `records` against `classifications` |
| AR-5 | Streamlit cold-start timeout | Minimal `requirements.txt`; heavy deps quarantined in `requirements-pipeline.txt` |
| AR-6 | Question analysis misreads intent | Restatement shown to the user before the answer; unclear plans fire all five channels rather than guessing; covered in `evals.md` |
| AR-11 | Verification layer rejects valid answers in a loop | Bounded to one regeneration, then the answer is served with an explicit "could not fully verify" banner rather than looping or failing silently |
| AR-7 | Clustering unstable across runs | Fixed random seeds; cluster assignments persisted with `run_id`, never recomputed live |
| AR-8 | Gold set too small for 33-code κ | At 2,000 records a 150–200 gold set is 8–10% of the corpus — proportionally strong. Stratified sampling over-weights rare codes; per-code agreement reported only where n permits, marked indicative elsewhere |
| AR-12 | Thin per-code counts read as confident findings | Minimum-n gate (§9.4): n ≥ 30 for a ranked claim, n ≥ 15 to appear at all; below that, greyed with the count shown |

---

## 13. What comes next

| Doc | Purpose |
|---|---|
| `edgecase.md` | ✅ **Written.** Failure modes per stage, with a silent-failure register and nine design requirements fed back into the build |
| `evals.md` | ✅ **Written.** Per-stage gates: 13 thresholds, invariants, gold metrics, adversarial probes, AC coverage map |
| `implementationplan.md` | Build sequence, each of the four stages gated by its own eval before deployment |
