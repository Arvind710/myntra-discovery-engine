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
