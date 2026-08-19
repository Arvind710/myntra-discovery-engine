-- =====================================================================
-- Myntra AI Discovery Engine — corpus schema
-- Source: architecture.md §4.1, plus the five deltas in
--         implementationplan.md Appendix A (marked [A.n] below).
-- Frozen at P0. A change here after data exists is a migration, not an edit.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. RAW MATERIAL
-- ---------------------------------------------------------------------

-- Every collected record lives here FOREVER, including ones later excluded.
-- [A.1] `exclusions` is a MARKING table, not a removal: FR-1.5/1.6 need the
-- exclusion log browsable *with its text*, and the gold sampling frame
-- (Appendix B) must be able to draw prefilter-rejected records.
CREATE TABLE IF NOT EXISTS records (
  record_id      TEXT PRIMARY KEY,          -- sha1(source || native_id) — idempotent re-ingest (EC-CLEAN-7)
  source         TEXT NOT NULL CHECK (source IN ('play','appstore','reddit','youtube','curated')),
  source_url     TEXT NOT NULL,             -- permalink — NFR-1. No record without one
  native_id      TEXT,
  author_hash    TEXT,                      -- salted hash, never the handle (NFR-7)
  created_at     TEXT,                      -- ISO8601, NULL where the source gives none (EC-COL-10)
  text_raw       TEXT NOT NULL,             -- verbatim. THIS is what the classifier reads (EC-CLEAN-6)
  text_clean     TEXT NOT NULL,             -- normalised copy, for matching/search only
  lang           TEXT,                      -- en|hi|hi-Latn|mixed|other|unknown — metadata only, never a drop reason (EC-CLEAN-4)
  rating         INTEGER,                   -- 1-5 where applicable
  thread_context TEXT,                      -- parent post title / video title
  collect_query  TEXT,                      -- what search surfaced it — bias auditing (EC-COL-12)
  text_available INTEGER NOT NULL DEFAULT 1, -- [A.2] EC-COL-14: paywalled/image-only curated items. 0 => NEVER quote
  collected_at   TEXT NOT NULL,
  ingest_run_id  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_records_source  ON records(source);
CREATE INDEX IF NOT EXISTS ix_records_author  ON records(author_hash);
CREATE INDEX IF NOT EXISTS ix_records_created ON records(created_at);

-- What was set aside and why. A finding in its own right (FR-1.6).
-- [A.1] FK into records: the row stays, it is merely marked.
CREATE TABLE IF NOT EXISTS exclusions (
  record_id TEXT NOT NULL REFERENCES records(record_id),
  source    TEXT NOT NULL,
  stage     TEXT NOT NULL CHECK (stage IN ('collect','clean','prefilter','relevance','classify')),
  reason    TEXT NOT NULL CHECK (reason IN (
              'dedupe/exact','dedupe/near','length','deleted','spam','farm',
              'prefilter','relevance','policy','parse_error','other')),
  detail    TEXT,
  run_id    TEXT NOT NULL,
  PRIMARY KEY (record_id, stage, reason, run_id)
);
CREATE INDEX IF NOT EXISTS ix_exclusions_reason ON exclusions(reason);

-- Records that survived every filter. Analysis denominators use THIS.
-- The Data Bank and the gold sampler use the base table.
CREATE VIEW IF NOT EXISTS retained AS
  SELECT r.* FROM records r
  WHERE NOT EXISTS (SELECT 1 FROM exclusions e WHERE e.record_id = r.record_id);

-- EC-CLEAN-1 / P1-3: cross-author similarity is MEASURED and REPORTED as
-- consensus strength. It is never used to remove a record. Fifty people
-- independently saying "sizes run small" IS the finding.
CREATE TABLE IF NOT EXISTS consensus (
  record_id             TEXT PRIMARY KEY REFERENCES records(record_id),
  max_jaccard_xauthor   REAL,    -- highest similarity to any DIFFERENT author's record
  n_similar_xauthor     INTEGER, -- how many distinct authors said something near-identical
  run_id                TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- 2. FILTERING
-- ---------------------------------------------------------------------

-- [A.5] Prefilter decisions persisted so S2-MET-6 can ask "would the
-- prefilter have kept this gold-relevant record?" without re-running it.
-- EC-PRE-1: a record dropped here is invisible to every downstream metric.
CREATE TABLE IF NOT EXISTS prefilter (
  record_id       TEXT NOT NULL REFERENCES records(record_id),
  passed          INTEGER NOT NULL,   -- 0/1 — union of the two gates
  lexicon_hit     INTEGER NOT NULL,
  embed_score     REAL,               -- cosine vs exemplar set
  embed_hit       INTEGER NOT NULL,
  run_id          TEXT NOT NULL,
  PRIMARY KEY (record_id, run_id)
);

-- LLM pass 0.
CREATE TABLE IF NOT EXISTS relevance (
  record_id       TEXT NOT NULL REFERENCES records(record_id),
  is_relevant     INTEGER NOT NULL,
  reason          TEXT NOT NULL,
  confidence      REAL NOT NULL,
  secondhand      INTEGER NOT NULL DEFAULT 0, -- [A.2] EC-REL-4/5: opinion about others.
                                              -- EXCLUDED from counterfactual + workaround analysis
  myntra_specific INTEGER NOT NULL DEFAULT 1, -- [A.2] EC-REL-6: 0 => generic/competitor. Assumption A-4 flag
  run_id          TEXT NOT NULL,
  PRIMARY KEY (record_id, run_id)
);

-- ---------------------------------------------------------------------
-- 3. CLASSIFICATION (Track A — deductive)
-- ---------------------------------------------------------------------

-- One row per (record, code) — multi-label by construction (FR-2.3).
-- [A.4] chunk_index: long records (EC-COL-5) are chunked AT CLASSIFICATION
-- TIME ONLY and never become extra rows in `records`. Codes are unioned to
-- record level for all analysis; chunk_index locates an evidence_span
-- inside a long post.
CREATE TABLE IF NOT EXISTS classifications (
  record_id     TEXT NOT NULL REFERENCES records(record_id),
  code          TEXT NOT NULL,          -- A1.1 … D4, or Z-99
  chunk_index   INTEGER NOT NULL DEFAULT 0,
  confidence    REAL NOT NULL,
  evidence_span TEXT NOT NULL,          -- EXACT substring of text_raw — T-6, absolute (EC-CLS-6)
  reasoning     TEXT,                   -- audit trail (NFR-4) + confusion analysis input
  is_blocking   INTEGER NOT NULL DEFAULT 0,
  run_id        TEXT NOT NULL,
  PRIMARY KEY (record_id, code, chunk_index, run_id)
);
CREATE INDEX IF NOT EXISTS ix_class_code ON classifications(code);

-- Record-level attributes (FR-5.3).
CREATE TABLE IF NOT EXISTS record_meta (
  record_id           TEXT NOT NULL REFERENCES records(record_id),
  stages              TEXT,             -- JSON array, e.g. ["C"] or ["B","C"]
  blocking_code       TEXT,
  -- 'na' is a legitimate phase: the three-value enum (Eliminator/Confidence/
  -- Trigger) is defined in problemstatement.md §5.2 as a STAGE C attribute.
  -- It fits all of C and D and the Stage A trigger codes, but not Stage B
  -- retrieval friction or the A access codes -- those are Defer-outcome
  -- structural barriers, and labelling them 'eliminator' would break the
  -- Eliminator => Exit invariant while 'trigger'/'confidence' would be false.
  blocking_phase      TEXT CHECK (blocking_phase IN ('eliminator','confidence','trigger','na') OR blocking_phase IS NULL),
  outcome             TEXT CHECK (outcome IN ('exit','defer','na') OR outcome IS NULL),
  segment             TEXT CHECK (segment IN ('S1','S2','S3','unknown') OR segment IS NULL),
  segment_conf        REAL,             -- < 0.6 => segment must be 'unknown' (EC-CLS-10)
  workaround          INTEGER,
  workaround_text     TEXT,
  workaround_effort   INTEGER,          -- 1-3
  counterfactual      INTEGER,          -- "I'd have bought it if…"
  counterfactual_text TEXT,
  intensity           INTEGER,          -- 1-5
  n_codes             INTEGER,          -- > 5 flagged for gold review (EC-CLS-2)
  run_id              TEXT NOT NULL,
  PRIMARY KEY (record_id, run_id)
);

-- EC-CLS-14/15: malformed JSON or content-policy refusal. Never dropped silently.
CREATE TABLE IF NOT EXISTS quarantine (
  record_id    TEXT NOT NULL REFERENCES records(record_id),
  stage        TEXT NOT NULL,
  error        TEXT NOT NULL,
  raw_response TEXT,
  run_id       TEXT NOT NULL,
  PRIMARY KEY (record_id, stage, run_id)
);

-- ---------------------------------------------------------------------
-- 4. CLUSTERING (Track B — inductive, blind to the codebook)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS clusters (
  record_id   TEXT NOT NULL REFERENCES records(record_id),
  cluster_id  INTEGER NOT NULL,      -- -1 = HDBSCAN noise
  probability REAL,
  space       TEXT NOT NULL DEFAULT 'all' CHECK (space IN ('all','z99')), -- Z-99 clustered separately (FR-5.4)
  run_id      TEXT NOT NULL,
  PRIMARY KEY (record_id, space, run_id)
);

CREATE TABLE IF NOT EXISTS cluster_labels (
  cluster_id  INTEGER NOT NULL,
  space       TEXT NOT NULL DEFAULT 'all',
  label       TEXT NOT NULL,
  description TEXT,
  size        INTEGER NOT NULL,
  exemplar_ids TEXT,                 -- JSON array of record_ids
  run_id      TEXT NOT NULL,
  PRIMARY KEY (cluster_id, space, run_id)
);

-- ---------------------------------------------------------------------
-- 5. HUMAN GROUND TRUTH (AC-9)
-- ---------------------------------------------------------------------

-- [A.3] PK is (record_id, pass_no). T-13 / EC-VAL-1 needs 20 records
-- labelled TWICE in separate sittings to measure labeller drift; a PK on
-- record_id alone would make the second label an overwrite.
-- Scoring uses pass_no = 1. T-13 compares pass 1 vs pass 2 on the repeats.
-- The labeller must not be told a record is a repeat.
CREATE TABLE IF NOT EXISTS gold (
  record_id   TEXT NOT NULL REFERENCES records(record_id),
  pass_no     INTEGER NOT NULL DEFAULT 1,
  sitting_id  TEXT NOT NULL,
  stratum     TEXT NOT NULL,          -- Appendix B stratum this record was drawn from
  is_relevant INTEGER NOT NULL,
  codes       TEXT NOT NULL,          -- JSON array
  segment     TEXT,
  labelled_at TEXT NOT NULL,
  notes       TEXT,                   -- EC-VAL-5: amendments recorded here, never silent
  PRIMARY KEY (record_id, pass_no)
);

-- ---------------------------------------------------------------------
-- 6. PROVENANCE (NFR-4)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS runs (
  run_id           TEXT PRIMARY KEY,
  stage            TEXT NOT NULL,
  started_at       TEXT NOT NULL,
  finished_at      TEXT,
  model            TEXT,
  prompt_version   TEXT,
  codebook_version TEXT,              -- EC-CLS-16: must be uniform within a run (S2-INV-5)
  n_input          INTEGER,
  n_output         INTEGER,
  input_tokens     INTEGER,
  output_tokens    INTEGER,
  cached_tokens    INTEGER,
  cost_usd         REAL,
  params_json      TEXT
);

-- EC-OPS-8 / X-4: the app reads a PINNED run, never "latest". A pipeline
-- re-run mid-demo must not change what an evaluator is looking at.
CREATE TABLE IF NOT EXISTS published (
  singleton   INTEGER PRIMARY KEY CHECK (singleton = 1),
  run_id      TEXT NOT NULL,
  published_at TEXT NOT NULL,
  note        TEXT
);

-- ---------------------------------------------------------------------
-- 7. MATERIALISED ANALYSIS (arch §4.2)
-- Design rule: the app performs NO aggregation over raw records.
-- Everything displayed is a SELECT from one of these. This is what
-- guarantees the charts and the chatbot cannot disagree.
-- Every table carries n and run_id (S2-INV-9).
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS analysis_code_prevalence (
  code TEXT NOT NULL, stage TEXT, phase TEXT, outcome TEXT,
  n INTEGER NOT NULL, n_distinct_authors INTEGER NOT NULL, -- EC-COL-9
  denominator INTEGER NOT NULL, share REAL NOT NULL,
  n_sources INTEGER, mean_confidence REAL,
  below_min_n INTEGER NOT NULL DEFAULT 0,   -- AR-12: n<30 => not a ranked claim
  run_id TEXT NOT NULL, PRIMARY KEY (code, run_id));

CREATE TABLE IF NOT EXISTS analysis_segment_code (
  segment TEXT NOT NULL, code TEXT NOT NULL,
  n INTEGER NOT NULL, n_distinct_authors INTEGER, denominator INTEGER NOT NULL,
  share REAL, coverage REAL NOT NULL,       -- S2-INV-10: stored, not inferred at render
  below_min_n INTEGER NOT NULL DEFAULT 0,
  run_id TEXT NOT NULL, PRIMARY KEY (segment, code, run_id));

CREATE TABLE IF NOT EXISTS analysis_cooccurrence (
  code_a TEXT NOT NULL, code_b TEXT NOT NULL,
  n_joint INTEGER NOT NULL, n_a INTEGER NOT NULL, n_b INTEGER NOT NULL,
  denominator INTEGER NOT NULL, lift REAL, pmi REAL,
  min_support_met INTEGER NOT NULL DEFAULT 0,
  run_id TEXT NOT NULL, PRIMARY KEY (code_a, code_b, run_id));

CREATE TABLE IF NOT EXISTS analysis_source_code (
  source TEXT NOT NULL, code TEXT NOT NULL,
  n INTEGER NOT NULL, n_distinct_authors INTEGER, denominator INTEGER NOT NULL,
  share REAL, js_divergence REAL,           -- per-source distribution vs pooled
  run_id TEXT NOT NULL, PRIMARY KEY (source, code, run_id));

CREATE TABLE IF NOT EXISTS analysis_stage_outcome (
  stage TEXT NOT NULL, outcome TEXT NOT NULL,
  n INTEGER NOT NULL, denominator INTEGER NOT NULL, share REAL,
  run_id TEXT NOT NULL, PRIMARY KEY (stage, outcome, run_id));

CREATE TABLE IF NOT EXISTS analysis_workaround (
  code TEXT NOT NULL,
  n_with_workaround INTEGER NOT NULL, n_code INTEGER NOT NULL,
  share REAL, mean_effort REAL, intensity_index REAL, -- mean(effort) × share
  run_id TEXT NOT NULL, PRIMARY KEY (code, run_id));

CREATE TABLE IF NOT EXISTS analysis_counterfactuals (
  code TEXT NOT NULL,
  n_counterfactual INTEGER NOT NULL, n_code INTEGER NOT NULL, share REAL,
  exemplar_ids TEXT,
  run_id TEXT NOT NULL, PRIMARY KEY (code, run_id));

CREATE TABLE IF NOT EXISTS analysis_cluster_code (
  cluster_id INTEGER NOT NULL, space TEXT NOT NULL DEFAULT 'all', code TEXT NOT NULL,
  n INTEGER NOT NULL, cluster_size INTEGER NOT NULL, code_size INTEGER NOT NULL,
  entropy_code_to_cluster REAL, entropy_cluster_to_code REAL,
  run_id TEXT NOT NULL, PRIMARY KEY (cluster_id, space, code, run_id));

CREATE TABLE IF NOT EXISTS analysis_evidence_strength (
  code TEXT NOT NULL,
  prevalence REAL, source_diversity REAL, counterfactual_rate REAL,
  workaround_rate REAL, mean_confidence REAL, recency REAL,
  composite REAL NOT NULL, n INTEGER NOT NULL,
  run_id TEXT NOT NULL, PRIMARY KEY (code, run_id));

CREATE TABLE IF NOT EXISTS analysis_opportunity (
  code TEXT NOT NULL, stage TEXT,
  prevalence REAL, intensity REAL, defer_share REAL,
  solvable_without_money REAL, evidence_strength REAL, segment_fit REAL,
  score REAL NOT NULL, rank INTEGER,
  n INTEGER NOT NULL,
  excluded INTEGER NOT NULL DEFAULT 0,  -- AC-12: C9 / S3 sized, then EXCLUDED
  exclusion_reason TEXT,
  run_id TEXT NOT NULL, PRIMARY KEY (code, run_id));

-- ---------------------------------------------------------------------
-- 8. SYNTHESIS (Phase 3)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS insights (
  insight_id   TEXT PRIMARY KEY,
  statement    TEXT NOT NULL,
  cites        TEXT NOT NULL,        -- JSON array of {table, key} — S3-INV-1: must resolve
  n            INTEGER,
  novelty      INTEGER DEFAULT 0,    -- outside H1-H15 / DH1-DH13 (AC-6)
  novelty_note TEXT,
  run_id       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hypotheses (
  hypothesis_id     TEXT PRIMARY KEY,
  statement         TEXT NOT NULL,
  codes             TEXT NOT NULL,   -- JSON array
  supporting_n      INTEGER NOT NULL,
  verbatim_ids      TEXT NOT NULL,   -- JSON array of record_ids
  source_diversity  INTEGER,
  confidence        TEXT,
  contradicting     TEXT NOT NULL,   -- S3-INV-3: non-empty, "none found" is a valid value
  falsifier         TEXT NOT NULL,   -- S3-INV-2 / AC-7: what would disprove it
  run_id            TEXT NOT NULL
);
