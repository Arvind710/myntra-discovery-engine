"""P0 gate -- Foundation & Freeze.

Nothing here produces a finding. Everything here is what stops a later
finding from being wrong.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.common import codebook as cb_mod

pytestmark = pytest.mark.phase0


# --- P0-1: schema applies clean, and is idempotent -------------------

def test_p0_1_schema_applies_clean(blank_db):
    tables = {r[0] for r in blank_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    required = {
        # arch §4.1 core
        "records", "exclusions", "relevance", "classifications", "record_meta",
        "clusters", "cluster_labels", "gold", "runs",
        # Appendix A deltas
        "prefilter", "consensus", "quarantine", "published",
        # arch §4.2 materialised analysis
        "analysis_code_prevalence", "analysis_segment_code", "analysis_cooccurrence",
        "analysis_source_code", "analysis_stage_outcome", "analysis_workaround",
        "analysis_counterfactuals", "analysis_cluster_code",
        "analysis_evidence_strength", "analysis_opportunity",
        # Phase 3
        "insights", "hypotheses",
    }
    assert required <= tables, f"missing tables: {sorted(required - tables)}"


def test_p0_1_retained_view_exists(blank_db):
    """[A.1] `retained` is how analysis gets its denominator without
    deleting rows the Data Bank and gold sampler still need."""
    views = {r[0] for r in blank_db.execute(
        "SELECT name FROM sqlite_master WHERE type='view'")}
    assert "retained" in views


def test_p0_1_schema_is_idempotent(schema_sql, tmp_path):
    con = sqlite3.connect(tmp_path / "twice.db")
    con.executescript(schema_sql)
    con.executescript(schema_sql)  # must not raise


def test_p0_1_appendix_a_deltas_present(blank_db):
    def cols(t):
        return {r[1] for r in blank_db.execute(f"PRAGMA table_info({t})")}

    # [A.2] flags edgecase.md mandates but arch §4.1 never allocated
    assert "text_available" in cols("records"), "EC-COL-14"
    assert {"secondhand", "myntra_specific"} <= cols("relevance"), "EC-REL-4/5/6"
    # [A.3] gold must hold two passes of the same record for T-13
    gold_pk = [r[1] for r in blank_db.execute("PRAGMA table_info(gold)") if r[5]]
    assert set(gold_pk) == {"record_id", "pass_no"}, "EC-VAL-1 needs repeated items"
    # [A.4] chunked long records
    assert "chunk_index" in cols("classifications"), "EC-COL-5"
    # [A.5] prefilter decisions persisted so recall is measurable
    assert "passed" in cols("prefilter"), "EC-PRE-1 / S2-MET-6"


def test_p0_1_gold_accepts_two_passes_of_one_record(blank_db):
    """The T-13 intra-rater test is impossible if the second label overwrites."""
    blank_db.execute(
        "INSERT INTO records (record_id, source, source_url, text_raw, text_clean,"
        " collected_at, ingest_run_id) VALUES ('r1','reddit','http://x','t','t','now','run')")
    for p in (1, 2):
        blank_db.execute(
            "INSERT INTO gold (record_id, pass_no, sitting_id, stratum, is_relevant,"
            " codes, labelled_at) VALUES ('r1',?,?,'high_conf',1,'[\"C1\"]','now')",
            (p, f"sitting{p}"))
    assert blank_db.execute("SELECT count(*) FROM gold").fetchone()[0] == 2


def test_p0_1_exclusions_is_a_marking_table(blank_db):
    """[A.1] An excluded record STAYS in `records` and drops out of `retained`."""
    blank_db.execute(
        "INSERT INTO records (record_id, source, source_url, text_raw, text_clean,"
        " collected_at, ingest_run_id) VALUES ('r1','play','http://x','t','t','now','run')")
    blank_db.execute(
        "INSERT INTO exclusions (record_id, source, stage, reason, run_id)"
        " VALUES ('r1','play','prefilter','prefilter','run')")
    assert blank_db.execute("SELECT count(*) FROM records").fetchone()[0] == 1
    assert blank_db.execute("SELECT count(*) FROM retained").fetchone()[0] == 0


def test_p0_1_exclusion_reason_enum_enforced(blank_db):
    """S1-INV-5: every exclusion row carries a reason from the allowed enum."""
    blank_db.execute(
        "INSERT INTO records (record_id, source, source_url, text_raw, text_clean,"
        " collected_at, ingest_run_id) VALUES ('r1','play','http://x','t','t','now','run')")
    with pytest.raises(sqlite3.IntegrityError):
        blank_db.execute(
            "INSERT INTO exclusions (record_id, source, stage, reason, run_id)"
            " VALUES ('r1','play','clean','because-i-said-so','run')")


# --- P0-2: codebook completeness -------------------------------------

def test_p0_2_thirty_three_codes(codebook):
    assert len(codebook.scored_codes) == 33, "AC-10 / T-8"


def test_p0_2_stage_counts(codebook):
    got = {s: len(codebook.by_stage(s)) for s in ("A", "B", "C", "D")}
    assert got == {"A": 7, "B": 8, "C": 14, "D": 4}, f"problemstatement §5.3-5.6, got {got}"


@pytest.mark.parametrize("field", [
    "stage", "name", "phase", "outcome_default", "outcome_allowed",
    "journey_rank", "solvable_without_money", "boundary_note", "transferability",
])
def test_p0_2_no_code_missing_a_required_field(codebook, field):
    # Careful with falsiness: journey_rank 0 (C9) and solvable_without_money
    # False (C8) are both VALID values. Test for absence, not for truthiness.
    missing = [c for c, d in codebook.codes.items()
               if field not in d or d[field] is None or d[field] == ""]
    assert not missing, f"{field} missing on {missing}"


def test_p0_2_boundary_notes_are_substantive(codebook):
    """The pass-2 prompt carries these in full. A thin note does no work."""
    thin = {c: len(d["boundary_note"]) for c, d in codebook.codes.items()
            if len(d["boundary_note"]) < 120}
    assert not thin, f"boundary_note too thin: {thin}"


def test_p0_2_c1_c8_boundary_is_explicit(codebook):
    """EC-CLS-12: the known danger pair. Each note must name the other."""
    assert "C8" in codebook.codes["C1"]["boundary_note"]
    assert "C1" in codebook.codes["C8"]["boundary_note"]


def test_p0_2_crosswalk_covers_h1_to_h15(codebook):
    """problemstatement §5.7: nothing in the blueprint goes unclassified."""
    refs = set()
    for d in codebook.codes.values():
        refs.update(str(r) for r in d.get("blueprint_refs", []))
    missing = [f"H{i}" for i in range(1, 16) if f"H{i}" not in refs]
    assert not missing, f"blueprint hypotheses with no canonical home: {missing}"


# --- P0-3: journey_rank is a usable total order -----------------------

def test_p0_3_no_journey_rank_ties_within_stage(codebook):
    """Blocking code is a min() over journey_rank (arch §7.1). A tie makes
    it non-deterministic and breaks NFR-3 reproducibility."""
    for stage in ("A", "B", "C", "D"):
        ranks = [d["journey_rank"] for d in codebook.by_stage(stage)]
        assert len(set(ranks)) == len(ranks), f"stage {stage} has ties: {ranks}"


def test_p0_3_stage_c_gating_order(codebook):
    """Eliminators before Confidence before Trigger (problemstatement §5.5)."""
    ranked = [d for d in codebook.by_stage("C") if d["phase"] in ("eliminator", "confidence", "trigger")]
    order = {"eliminator": 0, "confidence": 1, "trigger": 2}
    seq = [order[d["phase"]] for d in ranked]
    assert seq == sorted(seq), f"C journey order violates phase gating: " \
                               f"{[(d['id'], d['phase']) for d in ranked]}"


# --- P0-4: contradiction matrix ---------------------------------------

def test_p0_4_contradiction_matrix_present(codebook):
    assert codebook.contradictions.get("mutually_exclusive_groups"), "EC-CLS-4"


def test_p0_4_c9_excludes_confidence_codes(codebook):
    """No live intent means no fit doubt. S2-INV-3 will assert this on data."""
    assert codebook.contradicts(["C9", "C1"]), "C9+C1 must be flagged"
    assert codebook.contradicts(["C11", "C2"]), "C11+C2 must be flagged"
    assert codebook.contradicts(["C9", "C11"]), "C9+C11 are different populations"


def test_p0_4_legitimate_pairs_not_flagged(codebook):
    """A contradiction matrix that fires on real combinations is worse than none."""
    for pair in (["C1", "C7"], ["C1", "C2"], ["C4", "C14"], ["C6", "C13"], ["C8", "C6"]):
        assert not codebook.contradicts(pair), f"{pair} is a legitimate combination"


def test_p0_4_eliminator_implies_exit_is_satisfiable(codebook):
    """S2-INV-4 asserts eliminator => exit. Every eliminator code must
    therefore ALLOW exit, or the invariant is unsatisfiable by construction."""
    for cid, d in codebook.codes.items():
        if d["phase"] == "eliminator":
            assert "exit" in d["outcome_allowed"], f"{cid} is an eliminator that forbids exit"


def test_p0_4_confidence_implies_defer_is_NOT_asserted(codebook):
    """Guards the reverse reading. C12 and D4 are confidence-phase with an
    exit outcome; an invariant asserting confidence => defer would fire on
    valid codebook entries. Recorded here so the P2 implementation cannot
    quietly add it."""
    exits = [c for c, d in codebook.codes.items()
             if d["phase"] == "confidence" and "exit" in d["outcome_allowed"]]
    assert exits, "expected C12/D4 -- if this is empty the codebook changed shape"


# --- P0-5: the freeze ---------------------------------------------------

def test_p0_5_codebook_is_frozen():
    assert cb_mod.FREEZE_FILE.exists(), "run: python pipeline/common/codebook.py freeze"
    frozen = json.loads(cb_mod.FREEZE_FILE.read_text())
    assert frozen["n_scored_codes"] == 33
    assert frozen["frozen_at"]


def test_p0_5_loader_rejects_a_mutated_codebook(tmp_path, monkeypatch):
    """FR-5.6 enforced in code, not in prose. An edit mid-run must RAISE,
    not silently split the corpus across two codebook versions (EC-CLS-16)."""
    src = cb_mod.CODEBOOK_DIR
    shadow = tmp_path / "codebook"
    shadow.mkdir()
    for name in ("codebook_v1.yaml", "segments_v1.yaml", "FROZEN.json"):
        (shadow / name).write_text((src / name).read_text())

    monkeypatch.setattr(cb_mod, "CODEBOOK_DIR", shadow)
    monkeypatch.setattr(cb_mod, "FREEZE_FILE", shadow / "FROZEN.json")
    cb_mod.load()  # unmutated: fine

    p = shadow / "codebook_v1.yaml"
    p.write_text(p.read_text().replace("min_n_visible: 15", "min_n_visible: 16"))
    with pytest.raises(cb_mod.CodebookError, match="MUTATED AFTER FREEZE"):
        cb_mod.load()


def test_p0_5_version_string_is_stamped_per_row(codebook):
    """EC-CLS-16 / S2-INV-5: what goes on every classification row."""
    # Format is <version>:<hash8> -- the length varies with the version
    # string (v1 -> v1.1), so assert the SHAPE, not a magic length.
    import re
    assert re.fullmatch(r"v\d+(\.\d+)?:[0-9a-f]{8}", codebook.version_string), \
        codebook.version_string


# --- P0-6: segments -----------------------------------------------------

def test_p0_6_segments_threshold_and_unknown_are_first_class(codebook):
    seg = codebook.segments
    assert seg["confidence_threshold"] == 0.60, "arch §6.3, open question #10"
    ids = {s["id"] for s in seg["segments"]}
    assert ids == {"S1", "S2", "S3", "unknown"}, "R-10: unknown is a LABEL, not a gap"
    s3 = next(s for s in seg["segments"] if s["id"] == "S3")
    assert s3.get("excluded_from_opportunity") is True, "AC-12 / EC-INS-3"


# --- P0-9: deployment hygiene -------------------------------------------

def test_p0_9_app_and_pipeline_requirements_stay_separate(root):
    """AR-5: heavy deps on Streamlit Cloud mean cold-start timeouts."""
    app = (root / "requirements.txt").read_text().lower()
    for heavy in ("umap", "hdbscan", "torch", "praw", "fasttext", "scikit-learn", "datasketch"):
        assert heavy not in app, f"{heavy} must not be in the app requirements"


def test_p0_9_embeddings_and_secrets_are_gitignored(root):
    ig = (root / ".gitignore").read_text()
    assert "embeddings.npy" in ig, "arch §2: embeddings NEVER ship to Streamlit"
    assert "secrets.toml" in ig


def test_p0_9_no_real_secrets_committed(root):
    """The risk is a secret being TRACKED, not one existing locally --
    .streamlit/secrets.toml and .env are supposed to exist on the dev box.
    Assert against git's index, which is what actually leaves the machine."""
    import subprocess
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True
    ).stdout.splitlines()
    leaked = [f for f in tracked
              if f.endswith((".env", "secrets.toml")) or f.endswith("embeddings.npy")]
    assert not leaked, f"secrets tracked by git: {leaked}"


# --- P0-8: fixtures authored NOW, before the code they will test ---------

def _load_jsonl(root: Path, name: str) -> list[dict]:
    p = root / "evals" / "fixtures" / name
    assert p.exists(), f"missing fixture {name}"
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def test_p0_8_dedupe_fixture_pins_both_directions(root):
    """S1-PROBE-1 is only meaningful if the fixture has 40 DISTINCT authors
    saying near-identical things, plus one author repeating themselves."""
    rows = _load_jsonl(root, "dedupe_consensus.jsonl")
    consensus = [r for r in rows if r["record_id"].startswith("fx-consensus")]
    same = [r for r in rows if r["record_id"].startswith("fx-sameauthor")]

    assert len(consensus) == 40
    assert len({r["author_hash"] for r in consensus}) == 40, \
        "cross-author consensus needs 40 distinct authors or the test proves nothing"
    assert all(r["expect_survives"] for r in consensus), "EC-CLEAN-1: all 40 must survive"

    assert len(same) == 5
    assert len({r["author_hash"] for r in same}) == 1
    assert sum(r["expect_survives"] for r in same) == 1, "4 of 5 must be removed"


def test_p0_8_relevance_fixture_covers_the_hard_boundary(root):
    """EC-REL-1 is the hardest call in the rubric and the one that skews the
    denominator silently. It must be over-represented, in BOTH directions."""
    rows = _load_jsonl(root, "relevance_boundary.jsonl")
    assert len(rows) >= 60, "evals.md §4 specifies 60 boundary cases"

    cats = {r["category"] for r in rows}
    assert {"past_experience_relevant", "past_experience_irrelevant"} <= cats

    pos = [r for r in rows if r["category"] == "past_experience_relevant"]
    neg = [r for r in rows if r["category"] == "past_experience_irrelevant"]
    assert len(pos) >= 10 and len(neg) >= 10, "both directions needed, or it tests a bias"
    assert all(r["is_relevant"] == 1 for r in pos)
    assert all(r["is_relevant"] == 0 for r in neg)

    # Not so skewed that a constant classifier scores well against T-8's 75%.
    share = sum(r["is_relevant"] for r in rows) / len(rows)
    assert 0.35 <= share <= 0.75, f"label balance {share:.0%} lets a constant answer pass"

    # The flags the pass must also set (EC-REL-4/5/6, Appendix A.2)
    assert any(r["secondhand"] == 1 for r in rows)
    assert any(r["myntra_specific"] == 0 for r in rows)

    # Corpus is code-mixed; the rubric must be exercised on it (EC-CLEAN-4)
    assert sum(1 for r in rows if any(w in r["text_raw"].lower()
               for w in ("nahi", "hain", "yaar", "bhool", "pichli", "kabhi", "gaya"))) >= 4


def test_p0_8_injection_fixture_covers_the_named_attacks(root):
    """T-11 is absolute. The probe set must cover every class in evals §8.3."""
    rows = _load_jsonl(root, "injection_records.jsonl")
    assert len(rows) >= 6
    attacks = {r["attack"] for r in rows}
    required = {"direct_override", "fake_system_role", "codebook_override",
                "fake_citation_markup", "prompt_exfiltration", "fabricate_statistic"}
    assert required <= attacks, f"missing attack classes: {sorted(required - attacks)}"
    assert all(r.get("assertion") for r in rows), "every payload needs a stated assertion"
    # Each payload must also carry real feedback, so a system that refuses
    # wholesale is caught as a false positive rather than praised.
    assert all(len(r["text_raw"]) > 40 for r in rows)


# --- A-4 transferability (codebook v1.1) --------------------------------

def test_platform_mechanical_codes_are_low_transferability(codebook):
    """Only 35.9% of the relevant corpus is Myntra-specific (measured).
    Generic online-fashion records are legitimate evidence per A-4, but a
    complaint about Ajio's wishlist UI says nothing about Myntra's. Stage B
    is entirely platform-mechanical and must never be ranked on pooled n."""
    for cid, d in codebook.codes.items():
        if d["stage"] == "B":
            assert d["transferability"] == "low", f"{cid} is wishlist-UI specific"
    for cid in ("C7", "C8", "D1", "D2", "D3"):
        assert codebook.codes[cid]["transferability"] == "low", \
            f"{cid} depends on Myntra's own policy/inventory/checkout"


def test_category_rooted_codes_are_high_transferability(codebook):
    """Brand sizing is inconsistent across the whole Indian market; photos
    flatter fabric everywhere; wardrobe fit is about the wearer. Generic
    records are near-full-strength evidence for these."""
    for cid in ("C1", "C2", "C3", "C5", "C10", "C12"):
        assert codebook.codes[cid]["transferability"] == "high", cid


def test_min_myntra_specific_n_gate_present(codebook):
    """A ranked claim on a low-transferability code is ranked on its
    Myntra-specific n, not the pooled n."""
    assert codebook.meta.get("min_myntra_specific_n_for_low", 0) >= 15
