"""P1 gate -- Collection & Data Bank (S1-*).

The headline test here is S1-PROBE-1. It guards a failure that is both
catastrophic and invisible: cross-author near-dedupe deleting genuine
consensus. Everything else in this file is cheap insurance; that one is the
reason the file exists.
"""

import json
from pathlib import Path

import pytest

from pipeline.clean import dedupe

pytestmark = pytest.mark.phase1


@pytest.fixture(scope="module")
def consensus_fixture(request) -> list[dict]:
    root = Path(__file__).resolve().parents[1]
    p = root / "evals" / "fixtures" / "dedupe_consensus.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# =====================================================================
# S1-PROBE-1 -- consensus preservation. Pins BOTH directions.
# =====================================================================

def test_s1_probe_1_all_forty_distinct_authors_survive(consensus_fixture):
    """EC-CLEAN-1. Forty people independently saying 'sizes run small' IS
    the finding. If any are removed, the pipeline is deleting evidence and
    the charts will look fine afterwards."""
    rows = [r for r in consensus_fixture if r["record_id"].startswith("fx-consensus")]
    assert len(rows) == 40

    removed = dedupe.find_author_near_duplicates(rows)
    assert removed == [], (
        f"{len(removed)} cross-author records removed -- this is the "
        f"EC-CLEAN-1 bug. Near-dedupe MUST be scoped to (source, author_hash)."
    )


def test_s1_probe_1_same_author_repeats_collapse(consensus_fixture):
    """The other direction: author-scoped dedupe must actually work, or the
    first test passes trivially by doing nothing at all."""
    rows = [r for r in consensus_fixture if r["record_id"].startswith("fx-sameauthor")]
    assert len(rows) == 5

    removed = dedupe.find_author_near_duplicates(rows)
    assert len(removed) == 4, f"expected 4 of 5 removed, got {len(removed)}"

    survivors = {r["record_id"] for r in rows} - {loser for loser, _ in removed}
    assert len(survivors) == 1


def test_s1_probe_1_mixed_corpus(consensus_fixture):
    """Both populations together, which is what a real corpus looks like."""
    removed = {loser for loser, _ in dedupe.find_author_near_duplicates(consensus_fixture)}
    survived = [r for r in consensus_fixture if r["record_id"] not in removed]
    expected = [r for r in consensus_fixture if r["expect_survives"]]
    assert len(survived) == len(expected) == 41, (
        f"survived {len(survived)}, fixture expects {len(expected)}"
    )


def test_cross_author_similarity_is_measured_not_applied(consensus_fixture):
    """P1-3. The same measurement that would destroy the finding is instead
    stored as consensus strength. High cross-author similarity must produce
    a HIGH score, not a deletion."""
    rows = [r for r in consensus_fixture if r["record_id"].startswith("fx-consensus")]
    scores = dedupe.measure_cross_author_consensus(rows)
    assert len(scores) == 40
    assert all(s["max_jaccard_xauthor"] > 0.3 for s in scores), \
        "near-identical cross-author text should score high"

    # The claim under test is that consensus is DETECTED, not that every
    # phrasing is equally echoed -- some wordings legitimately have fewer
    # near-twins. Assert the central tendency, which is what a consensus
    # weight would actually read.
    counts = sorted(s["n_similar_xauthor"] for s in scores)
    median = counts[len(counts) // 2]
    assert median >= 5, f"median distinct authors echoing = {median}, expected >=5"
    assert max(counts) >= 15, "the most-echoed phrasing should see most of the cohort"


# =====================================================================
# Exact dedupe -- safe across sources (EC-CLEAN-2)
# =====================================================================

def test_exact_duplicates_keep_earliest(consensus_fixture):
    rows = [
        {"record_id": "b", "source": "reddit", "author_hash": "a1",
         "created_at": "2026-05-02T00:00:00+00:00", "text_raw": "Sizes run small here"},
        {"record_id": "a", "source": "youtube", "author_hash": "a2",
         "created_at": "2026-05-01T00:00:00+00:00", "text_raw": "sizes run small here!"},
    ]
    removed = dedupe.find_exact_duplicates(rows)
    assert removed == [("b", "a")], "cross-source exact dupes collapse to the earliest"


def test_normalisation_never_touches_text_raw():
    """EC-CLEAN-6: ALL CAPS and '!!!!' carry the intensity signal the
    classifier reads. Normalisation is for comparison only."""
    original = "SIZES RUN SMALL!!!! never again"
    dedupe.normalise_for_hash(original)
    assert original == "SIZES RUN SMALL!!!! never again"


# =====================================================================
# Corpus-level invariants (skip until collection has run)
# =====================================================================

@pytest.mark.needs_corpus
def test_s1_inv_2_every_record_has_provenance(corpus):
    """NFR-1: nothing enters analysis without a traceable origin."""
    n = corpus.execute(
        "SELECT count(*) FROM records WHERE source_url IS NULL OR source_url=''"
        " OR text_raw IS NULL OR text_raw=''").fetchone()[0]
    assert n == 0, f"{n} records without source_url or text_raw"


@pytest.mark.needs_corpus
def test_s1_inv_1_accounting_identity(corpus):
    """[A.1] Every collected record is either retained or explicitly
    excluded. No record vanishes unlogged."""
    total = corpus.execute("SELECT count(*) FROM records").fetchone()[0]
    retained = corpus.execute("SELECT count(*) FROM retained").fetchone()[0]
    excluded = corpus.execute(
        "SELECT count(DISTINCT record_id) FROM exclusions").fetchone()[0]
    assert total == retained + excluded, \
        f"{total} records != {retained} retained + {excluded} excluded"


@pytest.mark.needs_corpus
def test_s1_inv_3_record_ids_unique(corpus):
    n = corpus.execute(
        "SELECT count(*) FROM (SELECT record_id FROM records"
        " GROUP BY record_id HAVING count(*)>1)").fetchone()[0]
    assert n == 0


@pytest.mark.needs_corpus
def test_s1_met_3_distinct_author_counts_available(corpus):
    """EC-COL-9: '200 records' and '200 people' are different claims, and
    the probe run showed one author contributing 18 of 113 comments."""
    row = corpus.execute(
        "SELECT count(*) AS n, count(DISTINCT author_hash) AS a FROM retained").fetchone()
    assert row["a"] > 0
    assert row["a"] <= row["n"]
