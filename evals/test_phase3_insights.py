"""P3 gate — Insights & Hypotheses (S3-*).

The invariants here guard the last hallucination surface in the pipeline.
Everything upstream is anchored — a classification carries a span verified as
an exact substring, a crosstab is arithmetic over those classifications — and
synthesis is the one step where a model writes prose. Prose can assert a number
that exists nowhere, so these tests check the database rather than the prompt.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.phase3

MIN_N_RANKED = 30


# ------------------------------------------------------------- pure unit tests
def test_citation_contract_rejects_an_unknown_table(corpus):
    from pipeline.synthesise import citations as ct
    with pytest.raises(ct.CitationError):
        ct.resolve(corpus, "records", "abc")


def test_citation_contract_rejects_a_wrong_arity_key(corpus):
    """The real failure mode. A model wrote `4 | Stuck Deciders`, reading the
    first data column as part of the key. Loosening the checker to accept that
    would have discarded the contract to work around a rendering bug."""
    from pipeline.synthesise import citations as ct
    with pytest.raises(ct.CitationError):
        ct.resolve(corpus, "analysis_segment_recommendation", "4|Stuck Deciders")


def test_numeral_verifier_catches_a_wrong_number():
    from pipeline.synthesise.verify import check_numerals
    row = {"code": "C2", "n": 241, "share": 0.2367, "denominator": 1018}
    assert check_numerals("C2 leads at 23.7% of 1,018 records (n=241).", [row]) == []
    assert check_numerals("C2 leads at 41% of 1,018 records.", [row]) == ["41%"]


def test_numeral_verifier_rejects_everything_when_nothing_is_cited():
    """An uncited claim is exactly what EC-INS-6 forbids; it must not pass by
    virtue of having no rows to contradict it."""
    from pipeline.synthesise.verify import check_numerals
    assert check_numerals("Fit doubt is 62% of the corpus.", []) == ["62%"]


def test_funnel_language_is_caught():
    """§8: the corpus measures discussion. An insight that renders a share as a
    drop-off rate is the single misreading this project most needs to prevent."""
    from pipeline.synthesise.insights import FUNNEL_LANGUAGE
    assert FUNNEL_LANGUAGE.search("24% of shoppers who saved an item dropped off")
    assert FUNNEL_LANGUAGE.search("a conversion rate of 24%")
    assert not FUNNEL_LANGUAGE.search("24% of save-decision discussion carries C2")


def test_priors_cover_all_28_pre_registered_hypotheses():
    """AC-6's bar is H1–H15 / DH1–DH13. If a blueprint_ref were lost in a
    codebook edit the bar would quietly drop, and novelty would get easier to
    claim for a reason unrelated to the corpus."""
    from pipeline.synthesise.priors import build, EXPECTED
    doc = build()
    assert doc["n_priors"] == 28
    assert [p["id"] for p in doc["priors"]] == EXPECTED
    assert all(p["codes"] for p in doc["priors"])


def test_sensitivity_is_seeded_and_reproducible():
    """NFR-3. A robustness figure that moves between runs cannot support a
    claim in a deck."""
    from pipeline.synthesise.opportunity import sensitivity, COMPONENTS
    rows = [{"code": f"C{i}", "rank": i,
             **{c: (i * 0.07 + j * 0.03) % 1 for j, c in enumerate(COMPONENTS)}}
            for i in range(1, 6)]
    a = sensitivity(rows, draws=200)
    b = sensitivity(rows, draws=200)
    assert [(r["code"], r["top_share"]) for r in a] == [(r["code"], r["top_share"]) for r in b]


def test_unranked_codes_are_excluded_from_the_sensitivity_draw():
    """S3-INV-5 again, from the other side: a code with no rank must not be
    able to win a perturbed weighting and appear as a robust opportunity."""
    from pipeline.synthesise.opportunity import sensitivity, COMPONENTS
    rows = [{"code": "RANKED", "rank": 1, **{c: 0.5 for c in COMPONENTS}},
            {"code": "RANKED2", "rank": 2, **{c: 0.4 for c in COMPONENTS}},
            {"code": "THIN", "rank": None, **{c: 0.99 for c in COMPONENTS}}]
    assert "THIN" not in {r["code"] for r in sensitivity(rows, draws=50)}


# ------------------------------------------------------------------ invariants
@pytest.mark.needs_corpus
def test_s3_inv_1_every_insight_cites_a_row_that_exists(corpus):
    """EC-INS-6, absolute. Insight generation reads only the analysis tables;
    this asserts that what it wrote still resolves against them."""
    from pipeline.synthesise import citations as ct
    rows = list(corpus.execute("SELECT insight_id, cites FROM insights"))
    if not rows:
        pytest.skip("no insights generated yet")
    bad = []
    for r in rows:
        cites = json.loads(r["cites"])
        _, failures = ct.check(corpus, cites)
        if failures:
            bad.append((r["insight_id"], failures))
    assert not bad, f"insights with unresolvable citations: {bad}"


@pytest.mark.needs_corpus
def test_every_numeral_in_a_stored_insight_is_supported_by_a_cited_row(corpus):
    """Stronger than S3-INV-1 and the reason it is worth having: a citation
    proves the sentence POINTS AT a row, not that it reports what the row says."""
    from pipeline.synthesise import citations as ct
    from pipeline.synthesise.verify import check_numerals
    rows = list(corpus.execute("SELECT insight_id, statement, cites FROM insights"))
    if not rows:
        pytest.skip("no insights generated yet")
    bad = []
    for r in rows:
        resolved, _ = ct.check(corpus, json.loads(r["cites"]))
        unsupported = check_numerals(r["statement"], resolved)
        if unsupported:
            bad.append((r["insight_id"], unsupported))
    assert not bad, f"insights asserting numbers no cited row supports: {bad}"


@pytest.mark.needs_corpus
def test_no_stored_insight_states_a_share_as_a_funnel_measure(corpus):
    from pipeline.synthesise.insights import FUNNEL_LANGUAGE
    bad = [(r["insight_id"], FUNNEL_LANGUAGE.search(r["statement"] + " " + (r["so_what"] or "")).group(0))
           for r in corpus.execute("SELECT insight_id, statement, so_what FROM insights")
           if FUNNEL_LANGUAGE.search(r["statement"] + " " + (r["so_what"] or ""))]
    assert not bad, f"proxy discipline violated: {bad}"


@pytest.mark.needs_corpus
def test_s3_inv_2_every_hypothesis_has_a_falsifier(corpus):
    """AC-7. A causal claim with no kill condition is not a hypothesis."""
    rows = list(corpus.execute("SELECT hypothesis_id, falsifier FROM hypotheses"))
    if not rows:
        pytest.skip("no hypotheses generated yet")
    bad = [r["hypothesis_id"] for r in rows if not (r["falsifier"] or "").strip()]
    assert not bad, f"hypotheses with no falsifier: {bad}"
    thin = [r["hypothesis_id"] for r in rows if len((r["falsifier"] or "").split()) < 12]
    assert not thin, (f"falsifiers too thin to run: {thin} — a falsifier must name an "
                      "observation someone could actually collect")


@pytest.mark.needs_corpus
def test_s3_inv_3_every_hypothesis_records_contradicting_evidence(corpus):
    """'None found' is a legitimate value; empty is not. The distinction is the
    whole point — one says the question was asked."""
    rows = list(corpus.execute("SELECT hypothesis_id, contradicting FROM hypotheses"))
    if not rows:
        pytest.skip("no hypotheses generated yet")
    bad = [r["hypothesis_id"] for r in rows if not (r["contradicting"] or "").strip()]
    assert not bad, f"hypotheses with no contradicting-evidence field: {bad}"


@pytest.mark.needs_corpus
def test_hypothesis_verbatims_are_verified_spans_of_records_in_the_corpus(corpus):
    """T-6 reaches into synthesis. A quote that is not an exact substring of
    its record is not evidence, and a verbatim id pointing at an excluded or
    unquotable record must never reach the page."""
    rows = list(corpus.execute("SELECT hypothesis_id, verbatim_ids FROM hypotheses"))
    if not rows:
        pytest.skip("no hypotheses generated yet")
    bad = []
    for r in rows:
        for rid in json.loads(r["verbatim_ids"] or "[]"):
            ok = corpus.execute("""
                SELECT 1 FROM classifications cl JOIN records rec
                  ON rec.record_id = cl.record_id
                WHERE cl.record_id = ? AND cl.span_verified = 1 AND rec.text_available = 1
                  AND NOT EXISTS (SELECT 1 FROM exclusions e WHERE e.record_id = rec.record_id)
                LIMIT 1""", (rid,)).fetchone()
            if not ok:
                bad.append((r["hypothesis_id"], rid))
    assert not bad, f"verbatims that are not quotable verified evidence: {bad}"


@pytest.mark.needs_corpus
def test_hypothesis_supporting_counts_are_computed_not_asserted(corpus):
    """The model is not allowed to write its own evidence count. This re-derives
    every one from the classifications and requires an exact match."""
    from pipeline.synthesise.hypotheses import evidence_for
    rows = list(corpus.execute(
        "SELECT hypothesis_id, codes, supporting_n, source_diversity FROM hypotheses"))
    if not rows:
        pytest.skip("no hypotheses generated yet")
    for r in rows:
        ev = evidence_for(corpus, json.loads(r["codes"]))
        assert ev["supporting_n"] == r["supporting_n"], r["hypothesis_id"]
        assert ev["source_diversity"] == r["source_diversity"], r["hypothesis_id"]


@pytest.mark.needs_corpus
def test_s3_inv_4_c9_and_collectors_are_sized_then_excluded(corpus):
    """AC-12 / EC-INS-3. Two claims, and only one of them is visible in the
    `excluded` flag. The size must be stored too, or an exclusion is
    indistinguishable from an omission."""
    rows = {r["bucket"]: dict(r) for r in corpus.execute("SELECT * FROM analysis_addressable")}
    if not rows:
        pytest.skip("opportunity has not run yet")
    for bucket in ("c9_no_live_intent", "collectors"):
        assert bucket in rows, f"{bucket} was never sized"
        assert rows[bucket]["n"] > 0, f"{bucket} sized at zero — check the derivation"
        assert rows[bucket]["excluded"] == 1, f"{bucket} was sized but not excluded"
    assert (rows["addressable"]["n"]
            == rows["corpus"]["n"] - rows["c9_no_live_intent"]["n"]
            - rows["collectors"]["n"] + rows["overlap"]["n"]), \
        "addressable population does not reconcile with the sized exclusions"

    c9 = corpus.execute(
        "SELECT excluded FROM analysis_opportunity WHERE code = 'C9'").fetchone()
    assert c9 and c9["excluded"] == 1, "C9 is not flagged excluded in the opportunity table"


@pytest.mark.needs_corpus
def test_s3_inv_5_nothing_below_the_minimum_n_floor_is_ranked(corpus):
    """AR-12. A ranked claim needs n >= 30; a thin code may be scored and shown,
    never ranked."""
    bad = [(r["code"], r["n"]) for r in corpus.execute(
        "SELECT code, n, rank FROM analysis_opportunity WHERE rank IS NOT NULL")
        if r["n"] < MIN_N_RANKED]
    assert not bad, f"ranked on n below {MIN_N_RANKED}: {bad}"


@pytest.mark.needs_corpus
def test_ranked_opportunities_exclude_the_non_addressable_codes(corpus):
    rows = list(corpus.execute(
        "SELECT code FROM analysis_opportunity WHERE rank IS NOT NULL AND excluded = 1"))
    assert not rows, f"excluded codes carry a rank: {[r['code'] for r in rows]}"


@pytest.mark.needs_corpus
def test_opportunity_ranks_are_a_dense_total_order(corpus):
    ranks = sorted(r["rank"] for r in corpus.execute(
        "SELECT rank FROM analysis_opportunity WHERE rank IS NOT NULL"))
    assert ranks == list(range(1, len(ranks) + 1)), f"ranks are not 1..n: {ranks}"


@pytest.mark.needs_corpus
def test_every_opportunity_component_is_on_the_unit_interval(corpus):
    """Weights are only comparable if the things they multiply are. If a
    component escaped [0,1] the sliders would be measuring the scaling."""
    from pipeline.synthesise.opportunity import COMPONENTS
    for r in corpus.execute("SELECT * FROM analysis_opportunity"):
        for c in COMPONENTS:
            v = r[c]
            assert v is None or 0.0 <= v <= 1.0, f"{r['code']}.{c} = {v}"


# ----------------------------------------------------------------- metrics
@pytest.mark.needs_corpus
def test_s3_met_1_at_least_one_insight_is_confirmed_novel(corpus):
    """AC-6. The flag is the BY-HAND verdict from
    `codebook/novelty_verdicts.yaml`, not the similarity filter — evals.md is
    explicit that similarity is a filter and not a verdict."""
    rows = list(corpus.execute(
        "SELECT insight_id, novelty, novelty_note FROM insights WHERE novelty = 1"))
    if not list(corpus.execute("SELECT 1 FROM insights LIMIT 1")):
        pytest.skip("no insights generated yet")
    assert rows, ("no insight is outside H1-H15 / DH1-DH13. That is a legitimate "
                  "result (EC-INS-7) but it must be REPORTED, not fixed by inventing "
                  "one — check the Z-99 clusters and the cluster-code reconciliation "
                  "first, since novelty usually hides there")
    assert all((r["novelty_note"] or "").strip() for r in rows), \
        "a novelty flag with no written justification is an assertion, not a verdict"


@pytest.mark.needs_corpus
def test_novelty_verdicts_still_match_the_insights_they_judge(corpus):
    """A verdict attached to a regenerated statement looks like a judgement that
    was never made. This is the guard that makes the hand review durable."""
    if not list(corpus.execute("SELECT 1 FROM insights LIMIT 1")):
        pytest.skip("no insights generated yet")
    import yaml
    doc = yaml.safe_load((ROOT / "codebook" / "novelty_verdicts.yaml").read_text())
    have = {r["insight_id"]: r["statement"] for r in corpus.execute(
        "SELECT insight_id, statement FROM insights")}
    ids = {v["id"] for v in doc["verdicts"]}
    assert ids == set(have), (
        f"verdicts and insights disagree — only in verdicts: {ids - set(have)}; "
        f"only in insights: {set(have) - ids}")

    def norm(t: str) -> str:
        return "".join(ch for ch in t.lower().replace("‑", "-").replace("‐", "-")
                       if ch.isalnum() or ch == " ")
    drifted = [v["id"] for v in doc["verdicts"]
               if not norm(have[v["id"]]).startswith(norm(v["statement_prefix"]))]
    assert not drifted, f"insights regenerated since the verdicts were written: {drifted}"


@pytest.mark.needs_corpus
def test_s3_met_2_weight_robustness_is_reported(corpus):
    """No floor — the number is the deliverable. Reporting 'the top opportunity
    survives 87% of plausible weightings' is a far stronger claim than asserting
    a ranking; reporting 40% makes the interviews the tiebreak. Either is a
    pass; silence is not."""
    rows = list(corpus.execute(
        "SELECT code, top_share, n_draws, perturbation FROM analysis_weight_sensitivity"
        " ORDER BY top_share DESC"))
    if not rows:
        pytest.skip("opportunity has not run yet")
    assert rows[0]["n_draws"] >= 1000, "evals.md specifies 1,000 draws"
    assert abs(rows[0]["perturbation"] - 0.30) < 1e-9, "evals.md specifies ±30%"
    assert abs(sum(r["top_share"] for r in rows) - 1.0) < 1e-6, \
        "top_share must be a distribution over the ranked codes"


@pytest.mark.needs_corpus
def test_s3_met_3_stage_inversion_is_computed_for_stage_a(corpus):
    """arch §7.3. Stage A is the one the corpus under-detects by construction,
    so it is the one the threshold has to exist for."""
    rows = {r["stage"]: dict(r) for r in corpus.execute(
        "SELECT * FROM analysis_stage_inversion")}
    if not rows:
        pytest.skip("opportunity has not run yet")
    assert "A" in rows, "no inversion threshold for Stage A"
    a = rows["A"]
    if a["inversion_factor"] is None:
        assert a["leader"] == "A"        # Stage A leading is the only excuse
    else:
        assert a["inversion_factor"] > 1.0
        assert a["fragile"] == int(a["inversion_factor"] <= 3.0)


@pytest.mark.needs_corpus
def test_the_stage_inversion_threshold_is_rendered_on_the_chart_itself(corpus):
    """S3-MET-3 says 'displayed on the chart', and a number that lives only in a
    caption is the one a reader skips. The 3x fragility line must be drawn.

    The chart moved from Insights to Analysis on 2026-08-22: Analysis is where
    the STAGE is chosen, Insights is where the BARRIER is chosen, and a test
    that defends a decision should sit with the decision. The requirement is
    unchanged -- the line is still drawn, on the page that needs it.
    """
    src = (ROOT / "app" / "views" / "analysis.py").read_text()
    assert "add_vline" in src and "3.0" in src, \
        "the fragility threshold is not drawn on the inversion chart"


@pytest.mark.needs_corpus
def test_segment_recommendation_records_which_matrix_carried_it(corpus):
    """EC-INS-8. segment × code is the sharper claim and is expected to be too
    sparse here. The fallback is pre-planned; what must never happen is a
    directional read being quoted later as a ranked one."""
    rows = list(corpus.execute("SELECT * FROM analysis_segment_recommendation"))
    if not rows:
        pytest.skip("opportunity has not run yet")
    assert all(r["basis"] in ("segment x code", "segment x stage") for r in rows)
    rec = [r for r in rows if r["recommended"] == 1]
    assert len(rec) == 1, f"expected exactly one recommended segment, got {len(rec)}"
    assert (rec[0]["rationale"] or "").strip(), "the recommendation has no rationale"
    if rec[0]["basis"] == "segment x code":
        assert rec[0]["rankable_cells"] >= 3, \
            "claimed a code-level basis without enough cells above the floor"


@pytest.mark.needs_corpus
def test_collectors_are_not_in_the_segment_recommendation(corpus):
    """They were removed from the addressable population, so recommending them
    would mean the exclusion did not reach this table."""
    from pipeline.synthesise.opportunity import COLLECTORS_SEGMENT
    rows = [r["segment_id"] for r in corpus.execute(
        "SELECT segment_id FROM analysis_segment_recommendation")]
    assert COLLECTORS_SEGMENT not in rows, \
        "Collectors appear in the segment recommendation despite being excluded"


# ----------------------------------------------------------------- artefacts
@pytest.mark.needs_corpus
def test_generated_artefacts_exist_and_carry_falsifiers(corpus):
    """FR-3.4. The point of generating these is that the interviews test what
    the corpus raised. A guide with no kill conditions in it has lost that."""
    art = ROOT / "data" / "artifacts"
    for name in ("interview_guide.md", "survey_instrument.md",
                 "problem_framing_canvas.md"):
        path = art / name
        assert path.exists(), f"{name} was not generated"
        text = path.read_text()
        assert len(text) > 1500, f"{name} is too thin to be usable"
    guide = (art / "interview_guide.md").read_text()
    assert "dies if" in guide, "the interview guide carries no kill conditions"
    hyp_ids = [r["hypothesis_id"] for r in corpus.execute(
        "SELECT hypothesis_id FROM hypotheses LIMIT 3")]
    for hid in hyp_ids:
        assert hid in guide, f"{hid} is not tested anywhere in the interview guide"


@pytest.mark.needs_corpus
def test_no_generated_artefact_proposes_a_monetary_remedy(corpus):
    """C-2 is binding on the OUTPUT, not only on the analysis. A survey item or
    interview probe offering a discount would smuggle the forbidden solution
    into the primary research."""
    import re
    banned = re.compile(r"\b(discount|coupon|cashback|voucher|promo code)\b", re.I)
    for name in ("interview_guide.md", "survey_instrument.md",
                 "problem_framing_canvas.md"):
        text = (ROOT / "data" / "artifacts" / name).read_text()
        for line in text.splitlines():
            m = banned.search(line)
            # The constraint may be NAMED as out of scope; it may not be offered.
            if m and not re.search(r"out of scope|forbid|never|not\s|no monetary|are out",
                                   line, re.I):
                pytest.fail(f"{name} proposes a monetary remedy: {line.strip()[:120]}")


# ------------------------------------------------- the page, from production's cwd
@pytest.mark.needs_corpus
def test_insights_page_renders_the_sliders_and_the_ranking(corpus):
    """Task 3.4 is "weights as LIVE sliders", and "the page did not crash" is not
    that. This drives the real script from the repo root — the cwd Streamlit
    Cloud uses — and asserts the six controls exist, the ranking table is drawn,
    and the fragility chart is there."""
    import os
    from streamlit.testing.v1 import AppTest
    from pipeline.synthesise.opportunity import COMPONENTS

    prev = os.getcwd()
    os.chdir(ROOT)
    try:
        at = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=180)
        at.switch_page("views/insights.py")
        at.run()
        assert not at.exception, at.exception[0].value
        assert len(at.slider) == len(COMPONENTS), (
            f"expected one slider per scoring component, got {len(at.slider)}")
        # Guards the readability property rather than a fixed wording: a control
        # labelled `defer_share` is the codebook talking to itself. Every slider
        # must read as English and carry its own explanation.
        for sl in at.slider:
            assert "_" not in sl.label, f"raw field name leaked into the UI: {sl.label!r}"
            assert sl.help and len(sl.help) > 40, f"slider {sl.label!r} explains nothing"
        assert at.dataframe, "the opportunity ranking table did not render"
    finally:
        os.chdir(prev)


@pytest.mark.needs_corpus
def test_moving_a_weight_slider_actually_changes_the_score(corpus):
    """The sliders must re-weight the stored components, not decorate the page.
    A slider that renders but does nothing is the worst of both worlds: it
    invites the reader to test the ranking and then lies to them."""
    import os
    from streamlit.testing.v1 import AppTest

    prev = os.getcwd()
    os.chdir(ROOT)
    try:
        at = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=240)
        at.switch_page("views/insights.py")
        at.run()
        before = at.dataframe[0].value["score"].tolist()
        # Zero every weight except solvability: a different question entirely,
        # so a different order is expected. Identical output means dead controls.
        keep = "Fixable without a discount"
        assert any(sl.label == keep for sl in at.slider), \
            f"expected a slider labelled {keep!r}: {[sl.label for sl in at.slider]}"
        for sl in at.slider:
            if sl.label != keep:
                sl.set_value(0.0)
        at.run()
        after = at.dataframe[0].value["score"].tolist()
        assert before != after, "the weight sliders do not affect the score"
    finally:
        os.chdir(prev)
