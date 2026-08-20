"""Analysis — the quantified barrier ranking, in the framework's codes.

Design rule from architecture.md §4.2: this page performs NO aggregation
over raw records. Everything is a SELECT from a materialised analysis_*
table, which is what guarantees the charts and the chatbot cannot disagree.

Every chart shows n. Every code shows its DISTINCT-AUTHOR count. Nothing is
rendered as a drop-off or conversion rate — these are shares of DISCUSSION,
and the difference is the whole of §8.
"""

import pandas as pd
import streamlit as st

from lib import charts, db, framework as F

st.title("Analysis")
st.caption("Every relevant record scored against the pre-registered codebook. "
           "Reported in the updated framework's codes.")

status, detail = db.db_status()
if status != "ok":
    # Report which condition actually holds. "Not collected yet" asserted a
    # cause the check never established, and read as a project that never ran.
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

prev = db.query("SELECT * FROM analysis_code_prevalence ORDER BY n DESC")
if prev.empty:
    st.info("Classification has not run yet."); st.stop()

denom = int(prev["denominator"].iloc[0])
prev["fw"] = prev["code"].map(F.to_framework)
prev["label"] = prev["code"].map(F.name_of)

st.warning(
    "**These are shares of discussion, not drop-off rates.** Public feedback measures "
    "who talks about what, how often and how intensely — not how many users a stage "
    "loses. Silent barriers are under-represented by construction: forgetting a wishlist "
    "produces no complaint. Read this as an evidence-weighted ranking, never as a funnel "
    "measurement.",
    icon="⚠️",
)

tab_rank, tab_seg, tab_sub, tab_co, tab_val = st.tabs(
    ["Barrier ranking", "Segments", "Sub-codes", "Compound barriers", "Validation"])

# ------------------------------------------------------------ ranking
with tab_rank:
    c1, c2, c3 = st.columns(3)
    c1.metric("Relevant records", f"{denom:,}")
    c2.metric("Codes with evidence", f"{int((prev['n'] > 0).sum())} of {len(prev)}")
    z = prev[prev["code"] == "Z-99"]
    if not z.empty:
        c3.metric("Residual (Z-99)", f"{float(z['share'].iloc[0]):.1%}",
                  help="Above 15% means the codebook is treated as incomplete (FR-5.4)")

    top = prev[(prev["n"] > 0) & (prev["code"] != "Z-99")].head(15).copy()
    top["display"] = top["fw"] + " · " + top["label"].str.slice(0, 34)
    st.plotly_chart(
        charts.bar(top.sort_values("n"), "display", "n",
                   title="Barrier prevalence — share of save-decision discussion",
                   n_col="n", orientation="h", height=520),
        width="stretch")
    st.caption("Grey bars fall below n=30 and are shown but not ranked (AR-12). "
               "Denominator is every relevant record, so shares sum above 100% — "
               "records are multi-labelled by design (FR-2.3).")

    show = top[["fw", "label", "n", "n_distinct_authors", "share", "n_sources", "stage"]]
    show.columns = ["code", "barrier", "records", "distinct authors", "share", "sources", "stage"]
    st.dataframe(show, width="stretch", hide_index=True)

    zero = prev[prev["n"] == 0]
    if not zero.empty:
        st.markdown("**Codes with zero evidence** — reported, not hidden (AC-10)")
        st.caption("A code with no evidence is a result. A code never *checked* is a hole. "
                   "Stage A is expected to under-report by construction.")
        st.write(", ".join(sorted(zero["fw"])))

# ------------------------------------------------------------ segments
with tab_seg:
    seg = db.query("""SELECT segment_id, segment_name, count(*) AS n
                      FROM segments_v2 GROUP BY segment_id ORDER BY segment_id""")
    if seg.empty:
        st.info("Segments not derived yet.")
    else:
        st.caption(
            "Derived structurally from three questions — is there intent, what is the "
            "horizon, have they decided — rather than inferred from stated motivation. "
            "That is why coverage is 100% where the earlier motivation-based "
            "segmentation reached 6.6%."
        )
        seg["label"] = seg["segment_id"].map(lambda i: F.SEGMENTS[i][0])
        cols = st.columns(len(seg))
        for col, (_, r) in zip(cols, seg.iterrows()):
            star = " ★" if r.segment_id == F.TARGET_SEGMENT else ""
            col.metric(f"{r.label}{star}", f"{int(r.n):,}", f"{r.n/denom:.1%}")

        st.plotly_chart(charts.bar(seg, "label", "n", title="Segment sizes", n_col="n"),
                        width="stretch")

        st.subheader(f"{F.SEGMENTS[F.TARGET_SEGMENT][0]} — the target segment")
        st.caption(F.SEGMENTS[F.TARGET_SEGMENT][1])
        sc = db.query("""SELECT * FROM analysis_segment_code_v2
                         WHERE segment_id = ? AND n >= 15 ORDER BY n DESC""",
                      (F.TARGET_SEGMENT,))
        if not sc.empty:
            base = dict(zip(prev["code"], prev["share"]))
            sc["fw"] = sc["code"].map(F.to_framework)
            sc["barrier"] = sc["code"].map(F.name_of)
            sc["lift"] = sc.apply(
                lambda r: r["share"] / base[r["code"]] if base.get(r["code"]) else None, axis=1)
            out = sc[["fw", "barrier", "n", "n_distinct_authors", "share", "lift"]]
            out.columns = ["code", "barrier", "records", "authors", "share of segment", "lift vs corpus"]
            st.dataframe(out, width="stretch", hide_index=True)
            st.caption("**Lift** is what makes this segment distinctive rather than merely "
                       "large. A barrier at 2.8× is characteristic of these users; one at "
                       "1.0× is simply common everywhere.")

# ------------------------------------------------------------ sub-codes
with tab_sub:
    # Reads the materialised roll-up, not `subcodes` directly. The raw table
    # holds TWO runs for C2 and C3 (a re-run after a prompt fix) over different
    # populations, and aggregating it here unioned them — which put C2.4 above
    # 100% of C2 once the counts were done properly. The roll-up takes the
    # latest run per theme and honours the corpus exclusions.
    subs = db.query("SELECT * FROM analysis_subcode ORDER BY theme, n DESC")
    if subs.empty:
        st.info("Sub-coding has not run yet.")
    else:
        st.caption("A theme's headline number does not say what to build. The sub-code does. "
                   "Sub-coding is multi-label, so shares within a theme sum above 100%.")
        for theme in subs["theme"].unique():
            d = subs[subs["theme"] == theme].copy()
            tot = int(d["n_theme"].iloc[0])
            st.markdown(f"**{F.to_framework(theme)} — {F.name_of(theme)}**  ·  n = {tot}")
            d["what it is"] = d.apply(lambda r: F.subcode_label(theme, r["subcode"]), axis=1)
            st.dataframe(d[["subcode", "what it is", "n", "share", "mean_confidence"]]
                         .rename(columns={"share": "share of theme",
                                          "mean_confidence": "confidence"}),
                         width="stretch", hide_index=True)

# ------------------------------------------------------- co-occurrence
with tab_co:
    co = db.query("""SELECT * FROM analysis_cooccurrence
                     WHERE min_support_met = 1 AND code_a <> 'Z-99' AND code_b <> 'Z-99'
                     ORDER BY lift DESC LIMIT 15""")
    if co.empty:
        st.info("No pairs above the minimum-support floor.")
    else:
        st.caption(
            "Ranked by **lift**, not by frequency. A high-lift pair means two barriers "
            "co-occur far more than chance — evidence they are one compound problem with "
            "one fix, rather than two independent ones."
        )
        co["pair"] = co["code_a"].map(F.to_framework) + " × " + co["code_b"].map(F.to_framework)
        co["a"] = co["code_a"].map(F.name_of)
        co["b"] = co["code_b"].map(F.name_of)
        st.dataframe(co[["pair", "a", "b", "n_joint", "lift", "pmi"]],
                     width="stretch", hide_index=True)

# -------------------------------------------------------- validation
with tab_val:
    st.subheader("Validation")
    st.caption("How do you know the classifier is right? This is the answer, with numbers. "
               "It lives beside the analysis it qualifies rather than in a corner of the nav.")

    runs = db.query("SELECT stage, model, n_output, cost_usd, codebook_version, started_at"
                    " FROM runs WHERE n_output > 0 ORDER BY started_at DESC LIMIT 12")
    st.markdown("**Pipeline provenance** — every pass, its model, and what it cost")
    st.dataframe(runs, width="stretch", hide_index=True)

    spans = db.query("SELECT sum(span_verified) AS ok, count(*) AS n FROM classifications")
    if not spans.empty and spans["n"].iloc[0]:
        ok, n = int(spans["ok"].iloc[0]), int(spans["n"].iloc[0])
        st.metric("Evidence spans verified as exact quotes", f"{ok/n:.1%}",
                  help="A span that is not an exact substring of the record is not "
                       "evidence and is never rendered as a quote (T-6).")

    # B-5 requires the gate reports to be published IN THE APP, and they were
    # not — the P2 write-up said "published to the Validation tab" when the tab
    # only held a hard-coded limitations list. An evaluator could not read what
    # the gate actually found without cloning the repository.
    from pathlib import Path as _P
    REPORTS = _P(__file__).resolve().parents[2] / "evals" / "reports"
    gates = sorted(REPORTS.glob("gate_P*.md"), reverse=True)
    if gates:
        st.markdown("**Exit gate reports** — what each phase's gate actually found, "
                    "including what it found failing")
        st.caption("A tick on Home means the gate passed, not that the page exists. "
                   "These are the documents behind the ticks.")
        for g in gates:
            with st.expander(g.stem.replace("_", " ").replace("gate ", "Gate ")):
                st.markdown(g.read_text())

    st.markdown("**Known limitations, stated rather than discovered**")
    st.markdown("""
- **Stage A is under-detected by construction.** Forgetting produces no complaint, so a
  low Stage A count is not evidence that Stage A is small.
- **Only ~36% of the corpus is Myntra-specific.** Platform-mechanical codes (Stage B,
  D1–D3, C7, C8) are ranked on their Myntra-specific count, not the pooled one.
- **The prefilter was removed after measurement.** It dropped 23% of relevant records
  while saving $2.49. The corpus now has 100% scoring coverage.
- **Reddit was collected through a third-party service** after its API proved
  unavailable. Disclosed rather than hidden.
- **A human agreed with the pipeline on 19 of 30 randomly drawn records** (63%, Wilson 95%
  CI 45–78%). Every one of the 11 disagreements fell on a record the filter **rejected** —
  all 9 records it accepted were confirmed. So what is in this corpus belongs here; the
  open question is what is missing.
- **The relevance rubric is deliberately narrow, and that is a scope choice, not an
  oversight.** It excludes post-purchase satisfaction and order/refund complaints. Six of
  those 11 are that exclusion working as written. Admitting them would raise the
  material/quality (C2) and returns-trust (C7) counts more than the others, so **the
  ranking is conditional on the rubric** — the weight-robustness figure on the Insights
  page tests the scoring, not this.
""")
