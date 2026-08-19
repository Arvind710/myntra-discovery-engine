"""P2 gate — Analysis (S2-*)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.phase2


def test_unicode_punctuation_does_not_break_span_check():
    """EC-CHAT-11. The corpus carries curly quotes, en-dashes and ellipses;
    models emit ASCII. Comparing raw strings marks identical words as
    paraphrases — which would fail T-6 for a formatting reason and hide the
    real paraphrases underneath the noise."""
    from pipeline.classify.codes import normalise
    text = "It’s about the fit — and silhouette… “nice”"
    quote = 'it\'s about the fit - and silhouette... "nice"'
    assert normalise(quote) in normalise(text)


def test_genuine_paraphrase_still_fails():
    """The unicode fix must not become a licence to paraphrase."""
    from pipeline.classify.codes import normalise
    assert normalise("they will go with anything") not in \
        normalise("I'm more concerned why you think these will go with anything")  # noqa: E501


@pytest.mark.needs_corpus
def test_s2_inv_2_no_unverified_span_is_citable(corpus):
    """T-6, absolute. A span that is not an exact substring of text_raw is
    NOT evidence. The row is kept and counted — the CODE assignment can be
    sound even when the quote is not — but span_verified=0 means no citation
    path may render it. This asserts the citable set is 100% exact."""
    from pipeline.classify.codes import normalise
    bad = 0
    for r in corpus.execute("""
        SELECT cl.evidence_span, rec.text_raw FROM classifications cl
        JOIN records rec ON rec.record_id = cl.record_id
        WHERE cl.span_verified = 1"""):
        if normalise(r["evidence_span"]) not in normalise(r["text_raw"]):
            bad += 1
    assert bad == 0, f"{bad} spans marked verified are not exact substrings"


@pytest.mark.needs_corpus
def test_unverified_span_rate_is_reported(corpus):
    """Not a threshold — a measurement. A rising rate means the prompt is
    drifting toward paraphrase and should be caught before it is large."""
    row = corpus.execute(
        "SELECT sum(span_verified) AS ok, count(*) AS n FROM classifications").fetchone()
    if not row["n"]:
        pytest.skip("no classifications yet")
    rate = 1 - row["ok"] / row["n"]
    assert rate < 0.15, f"unverified span rate {rate:.1%} — prompt is drifting"


@pytest.mark.needs_corpus
def test_s2_inv_1_no_relevant_record_has_zero_codes(corpus):
    """EC-CLS-1: an orphan sits in the denominator and contributes to no
    numerator. Forbidden state, enforced at write time."""
    n = corpus.execute("""
        SELECT count(*) FROM relevance v
        WHERE v.is_relevant = 1
          AND EXISTS (SELECT 1 FROM record_meta m WHERE m.record_id = v.record_id)
          AND NOT EXISTS (SELECT 1 FROM classifications c WHERE c.record_id = v.record_id)
    """).fetchone()[0]
    assert n == 0, f"{n} classified records carry zero codes"


@pytest.mark.needs_corpus
def test_s2_inv_3_no_contradictory_codes(corpus, codebook):
    """EC-CLS-4: C9/C11 are mutually exclusive with Confidence-phase codes.
    No live intent means no fit doubt."""
    from collections import defaultdict
    per = defaultdict(list)
    for r in corpus.execute("SELECT record_id, code FROM classifications"):
        per[r["record_id"]].append(r["code"])
    violations = [(rid, codebook.contradicts(cs)) for rid, cs in per.items()
                  if codebook.contradicts(cs)]
    assert not violations, f"{len(violations)} records carry contradictory codes"


@pytest.mark.needs_corpus
def test_s2_inv_4_eliminator_implies_exit(corpus, codebook):
    """An Eliminator is a hard gate — it produces exit, not defer. Coerced
    at write time from the codebook, so this asserts the coercion held."""
    bad = []
    for r in corpus.execute(
            "SELECT record_id, blocking_code, outcome FROM record_meta WHERE blocking_code IS NOT NULL"):
        d = codebook.codes.get(r["blocking_code"])
        if d and r["outcome"] and r["outcome"] not in d["outcome_allowed"]:
            bad.append((r["record_id"], r["blocking_code"], r["outcome"]))
    assert not bad, f"{len(bad)} records whose outcome the blocking code forbids: {bad[:3]}"


@pytest.mark.needs_corpus
def test_s2_inv_10_segment_below_threshold_is_unknown(corpus, codebook):
    """R-10 / EC-CLS-10: forcing a segment fabricates the entire
    segmentation. Below 0.6 the label must be unknown, enforced in code
    rather than trusted to the model."""
    thr = float(codebook.segments["confidence_threshold"])
    n = corpus.execute(
        "SELECT count(*) FROM record_meta WHERE segment NOT IN ('unknown') AND segment_conf < ?",
        (thr,)).fetchone()[0]
    assert n == 0, f"{n} records carry a segment below the {thr} threshold"


@pytest.mark.needs_corpus
def test_dropped_prefilter_leaves_no_exclusion_marks(corpus):
    """The prefilter was removed from the pipeline after S2-MET-6 measured
    recall at 76.6% against a T-5 floor of 95%. Removing a stage from the
    CODE does not remove the marks it already wrote: `exclusions` is a
    marking table ([A.1]), and the `retained` view subtracts every mark.

    The marks survived the drop once already, and the effect was silent —
    the pipeline read `records` directly (relevance.py) so classification
    was correct, while the app read `retained` and reported a corpus of
    4,031 instead of 8,647, hiding exactly the 281 relevant records the
    prefilter finding was about. A dropped stage must have its marks
    reversed, not merely stop running.
    """
    n = corpus.execute(
        "SELECT count(*) FROM exclusions WHERE stage='prefilter'").fetchone()[0]
    assert n == 0, (
        f"{n} prefilter exclusion marks remain; the prefilter is dropped, so "
        "these silently shrink every denominator the app reads")


@pytest.mark.needs_corpus
def test_every_classified_record_is_visible_in_retained(corpus):
    """The property, not a proxy for it: whatever the exclusion table says,
    a record that was classified must be reachable through the view the app
    renders from. Otherwise the charts describe a corpus the Data Bank
    cannot show, and no error is raised anywhere."""
    hidden = corpus.execute(
        "SELECT count(DISTINCT record_id) FROM classifications "
        "WHERE record_id NOT IN (SELECT record_id FROM retained)").fetchone()[0]
    assert hidden == 0, (
        f"{hidden} classified records are excluded from the `retained` view — "
        "the analysis counts them, the app cannot display them")


def test_label_page_is_blind_to_model_output():
    """AC-9 rests on the gold set being an INDEPENDENT judgement. If the
    labelling page can show what the classifier decided, agreement measures
    anchoring rather than accuracy — and every metric it feeds (T-1..T-4)
    improves while the classifier gets no better.

    Asserted structurally rather than by reading the UI: the page must not
    query any table holding model output. A reviewer can verify this claim in
    one grep, which is the point.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "tools" / "label_app.py").read_text()
    forbidden = ["classifications", "record_meta", "subcodes", "segments_v2",
                 "analysis_", "clusters"]
    # `relevance` needs a word-boundary check: the page legitimately uses the
    # word in its question text, but must never SELECT from the table.
    hits = [t for t in forbidden if t in src]
    assert not hits, (
        f"tools/label_app.py references model-output table(s) {hits} — the gold set "
        "would no longer be independent of the thing it grades")
    assert "FROM relevance" not in src and "JOIN relevance" not in src, \
        "tools/label_app.py reads the relevance table; the labeller must not see the verdict"


@pytest.mark.needs_corpus
def test_gold_frame_matches_appendix_b_as_amended(corpus):
    """The frame is drawn once and frozen. If it drifts, the metrics are
    computed over a different population than the one that was designed to
    make recall measurable."""
    want = {"z99": 20, "c1_c8": 20, "clf_low": 30, "clf_high": 40, "rel_zero": 50}
    got = dict(corpus.execute(
        "SELECT stratum, count(*) FROM gold_sample WHERE pass_no=1 GROUP BY stratum"))
    assert got == want, f"frame drifted: {got} != {want}"

    distinct = corpus.execute(
        "SELECT count(DISTINCT record_id) FROM gold_sample").fetchone()[0]
    assert distinct == 160, f"{distinct} distinct records, Appendix B specifies 160"

    reps = corpus.execute("SELECT count(*) FROM gold_sample WHERE pass_no=2").fetchone()[0]
    assert reps == 20, f"{reps} silent repeats, T-13/EC-VAL-1 specifies 20"

    # A repeat that is not also in sitting 1 measures nothing.
    orphan = corpus.execute(
        "SELECT count(*) FROM gold_sample r WHERE r.pass_no=2 AND NOT EXISTS ("
        " SELECT 1 FROM gold_sample s WHERE s.record_id=r.record_id"
        " AND s.pass_no=1 AND s.sitting_id='sitting-1')").fetchone()[0]
    assert orphan == 0, f"{orphan} repeats are not drawn from sitting 1"

    # rel_zero exists to make T-2 recall measurable; a classified record in it
    # would mean the pipeline did not actually discard it.
    bad = corpus.execute(
        "SELECT count(*) FROM gold_sample g JOIN classifications c USING (record_id)"
        " WHERE g.stratum='rel_zero'").fetchone()[0]
    assert bad == 0, f"{bad} rel_zero records were classified after all"
