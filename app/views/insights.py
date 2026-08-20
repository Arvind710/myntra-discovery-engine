"""Insights — the ranked opportunity, its sensitivity, and what would disprove it.

Design rule (arch §4.2): this page performs NO aggregation over raw records.
The one thing it recomputes is the opportunity SCORE, and only because the six
components are stored as columns — moving a slider re-weights numbers the
pipeline already produced. It never re-counts anything.

WHY THE WEIGHTS ARE SLIDERS
---------------------------
A single hard-coded ranking invites "why those weights?" and has no answer. A
reader who can move them and watch the ranking hold has been given the answer
before asking. A ranking that survives the sliders is a much stronger claim
than one asserted — and if it does not survive, that is the finding, and the
page says so rather than hiding it behind the defaults.
"""

import json

import pandas as pd
import streamlit as st

from lib import charts, db, framework as F, story as S

COMPONENTS = ["prevalence", "intensity", "defer_share",
              "solvable_without_money", "evidence_strength", "segment_fit"]

# Each slider's explanation comes from the shared vocabulary layer, so the same
# words describe the same metric wherever it appears in the app.
COMPONENT_HELP = {
    "prevalence": "How much of the addressable conversation raises this barrier, "
                  "scaled against the largest. " + S.explain("share"),
    "intensity": S.explain("workaround"),
    "defer_share": S.explain("defer"),
    "solvable_without_money": S.explain("solvable"),
    "evidence_strength": S.explain("evidence_strength"),
    "segment_fit": S.explain("segment_fit"),
}

COMPONENT_LABEL = {
    "prevalence": "How often it comes up",
    "intensity": "How hard people work around it",
    "defer_share": "How often intent survives",
    "solvable_without_money": "Fixable without a discount",
    "evidence_strength": "How well-supported",
    "segment_fit": "How specific to the target group",
}

st.title("What to do about it")
st.caption("Which barrier is worth solving, how sure we are, and what would prove "
           "us wrong.")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

opp = db.query("SELECT * FROM analysis_opportunity")
if opp.empty:
    st.info("Synthesis has not run yet — `pipeline/synthesise/opportunity.py`.")
    st.stop()

addr = db.query("SELECT * FROM analysis_addressable").set_index("bucket")
opp["fw"] = opp["code"].map(F.to_framework)
opp["barrier"] = opp["code"].map(F.name_of)

st.warning(
    "**Shares of discussion, not drop-off rates.** No user-level or funnel data exists "
    "in this project. A barrier's size here is how much it is *talked about*, weighted "
    "by how hard people work around it — and silent barriers are under-represented by "
    "construction. The Stage A panel below quantifies exactly how much that could "
    "matter.", icon="⚠️")

tab_opp, tab_sens, tab_seg, tab_hyp, tab_ins, tab_art = st.tabs(
    ["Opportunity", "How fragile is this?", "Who to build for",
     "Hypotheses & falsifiers", "Insights", "Research artefacts"])

# ---------------------------------------------------------------- opportunity
with tab_opp:
    st.subheader("The addressable population — sized before it was narrowed")
    st.caption(
        "AC-12. Two populations are not conversion problems and are removed from the "
        "opportunity. They are counted first, because how big they are is itself a "
        "finding: leaving them in inflates the opportunity, and dropping them silently "
        "loses the result.")
    cols = st.columns(4)
    for col, bucket in zip(cols, ["corpus", "c9_no_live_intent", "collectors", "addressable"]):
        if bucket in addr.index:
            r = addr.loc[bucket]
            col.metric(str(r["label"]).split(" — ")[0], f"{int(r['n']):,}",
                       f"{float(r['share_of_corpus']):.1%} of corpus",
                       delta_color="off", help=str(r["reason"]))
    st.caption(f"Removed together: {int(addr.loc['corpus','n']) - int(addr.loc['addressable','n'])} "
               f"records. The two exclusions overlap by {int(addr.loc['overlap','n'])}, so they "
               "are not additive.")

    st.divider()
    st.subheader("Weights — move them")
    st.caption("The score is a weighted sum of six stored components. Nothing is "
               "recounted when you move a slider; the components are re-weighted. "
               "If the ranking holds across settings you would accept, it is not an "
               "artefact of ours.")

    wcols = st.columns(3)
    weights = {}
    for i, comp in enumerate(COMPONENTS):
        weights[comp] = wcols[i % 3].slider(
            COMPONENT_LABEL[comp], 0.0, 2.0, 1.0, 0.05, help=COMPONENT_HELP[comp])
    if st.button("Reset to equal weights"):
        st.rerun()

    total_w = sum(weights.values()) or 1.0
    opp["live_score"] = sum(opp[c] * weights[c] for c in COMPONENTS) / total_w

    ranked = opp[(opp["excluded"] == 0) & (opp["rank"].notna())].copy()
    ranked = ranked.sort_values("live_score", ascending=False).reset_index(drop=True)
    ranked["live_rank"] = ranked.index + 1

    default_top = opp.loc[opp["rank"] == 1, "code"]
    if len(ranked) and len(default_top) and ranked.iloc[0]["code"] != default_top.iloc[0]:
        st.error(f"At these weights the top opportunity changes from "
                 f"**{F.to_framework(default_top.iloc[0])}** to "
                 f"**{ranked.iloc[0]['fw']}**.", icon="↕️")

    show = ranked.copy()
    show["display"] = show["code"].map(S.chart_label)
    st.plotly_chart(
        charts.bar(show.sort_values("live_score"), "display", "live_score",
                   title="Opportunity score — addressable barriers only", height=460,
                   orientation="h"),
        width="stretch")
    st.caption("Only barriers at n ≥ 30 are ranked (AR-12). Everything scored but "
               "unranked is listed below with its count.")

    show["what the shopper is thinking"] = show["code"].map(S.voice)
    tbl = show[["live_rank", "what the shopper is thinking", "n", "live_score"] + COMPONENTS]
    tbl.columns = (["#", "what the shopper is thinking", "records", "score"]
                   + [COMPONENT_LABEL[c] for c in COMPONENTS])
    st.dataframe(tbl, width="stretch", hide_index=True,
                 column_config={c: st.column_config.ProgressColumn(
                     c, min_value=0.0, max_value=1.0, format="%.2f")
                     for c in ["score"] + [COMPONENT_LABEL[c] for c in COMPONENTS]})

    excl = opp[(opp["excluded"] == 1) | (opp["rank"].isna())]
    if not excl.empty:
        with st.expander(f"Scored but not ranked — {len(excl)} codes, and why"):
            excl = excl.copy()
            excl["what the shopper is thinking"] = excl["code"].map(S.voice)
            e = excl[["what the shopper is thinking", "n", "excluded", "exclusion_reason"]].copy()
            e.columns = ["what the shopper is thinking", "records", "excluded", "reason"]
            st.dataframe(e.sort_values("records", ascending=False),
                         width="stretch", hide_index=True)

    st.info(
        "**Price ranks lower here than it does on prevalence, and that is the "
        "constraint doing its job.** C6 (framework C6) is the second-largest barrier by "
        "volume, but the assignment forbids monetary remedies — so it enters the score "
        "at half weight on solvability and does not lead. That is a statement about what "
        "this project is allowed to build, not a claim that price does not matter. It "
        "must be resolved into transparency, anchoring and timing, or reported as out "
        "of scope.", icon="💰")

# ------------------------------------------------------------------ fragility
with tab_sens:
    st.subheader("Weight robustness")
    sens = db.query("SELECT * FROM analysis_weight_sensitivity ORDER BY top_share DESC")
    if sens.empty:
        st.info("Sensitivity not computed.")
    else:
        top = sens.iloc[0]
        st.metric(f"{F.to_framework(top['code'])} holds first place in",
                  f"{float(top['top_share']):.1%}",
                  f"of {int(top['n_draws']):,} weightings perturbed ±{float(top['perturbation']):.0%}")
        if float(top["top_share"]) >= 0.75:
            st.success("The ranking survives reasonable disagreement about the weights. "
                       "This is a much stronger claim than a single asserted ranking.",
                       icon="✅")
        else:
            st.warning("The top two cannot be separated on this evidence. The honest "
                       "headline is a tie, and the interviews are the tiebreak rather "
                       "than a formality (EC-INS-1).", icon="⚖️")
        d = sens.copy()
        d["barrier"] = d["code"].map(S.voice)
        d = d[["barrier", "top_share", "top3_share", "mean_rank", "p05_rank", "p95_rank"]]
        d.columns = ["barrier", "held 1st place", "stayed in top 3",
                     "average rank", "best rank", "worst rank"]
        st.dataframe(d, width="stretch", hide_index=True)
        st.caption("`p05`–`p95` is the rank interval across the draws. A code whose "
                   "interval is a single number never moved.")

    st.divider()
    st.subheader("What if Stage A is under-reported?")
    inv = db.query("SELECT * FROM analysis_stage_inversion ORDER BY n DESC")
    if inv.empty:
        st.info("Inversion threshold not computed.")
    else:
        st.caption(
            "Forgetting produces no complaint, so the corpus under-detects Stage A by "
            "construction and a low Stage A count is **not** evidence that Stage A is "
            "small. Rather than accept the ranking or discard it, this is the "
            "multiplier by which each stage would have to be under-reported to overtake "
            "the leader. Roughly 2–3× is plausible for a silent barrier; beyond that "
            "the ranking is safe.")
        d = inv.copy()
        d["label"] = "Stage " + d["stage"]
        d["factor"] = d["inversion_factor"].fillna(0.0)
        lead = d.loc[d["inversion_factor"].isna(), "stage"]
        fig = charts.bar(d[d["inversion_factor"].notna()].sort_values("factor"),
                         "label", "factor", orientation="h", height=280,
                         title="Under-reporting needed to overtake stage "
                               f"{lead.iloc[0] if len(lead) else '?'} (×)")
        fig.add_vline(x=3.0, line_dash="dash", line_color="#D55E00",
                      annotation_text="3× — plausible for a silent barrier",
                      annotation_position="top")
        st.plotly_chart(fig, width="stretch")
        for _, r in inv[inv["inversion_factor"].notna()].iterrows():
            msg = (f"**Stage {r['stage']}** (n={int(r['n'])}) would need "
                   f"**{float(r['inversion_factor']):.1f}×** under-reporting to overtake "
                   f"stage {r['leader']} (n={int(r['leader_n'])}).")
            (st.warning if int(r["fragile"]) else st.write)(
                msg + ("  **That is plausible — treat the stage ranking as fragile.**"
                       if int(r["fragile"]) else ""))

# ------------------------------------------------------------------- segments
with tab_seg:
    rec = db.query("SELECT * FROM analysis_segment_recommendation ORDER BY score DESC")
    if rec.empty:
        st.info("Segment recommendation not computed.")
    else:
        winner = rec[rec["recommended"] == 1]
        if not winner.empty:
            w = winner.iloc[0]
            st.subheader(f"({int(w['segment_id'])}) {w['segment_name']}")
            st.success(str(w["rationale"]), icon="🎯")
            if str(w["basis"]) != "segment x code":
                st.warning(
                    "This rests on **segment × stage**, not segment × code — too few "
                    "code cells reach n ≥ 30. Code-level detail for this segment is "
                    "directional and must not be quoted as a ranked claim (EC-INS-8).",
                    icon="⚠️")
            dist = json.loads(w["distinctive"] or "[]")
            if dist:
                st.markdown("**What makes this segment distinctive, not merely large**")
                dd = pd.DataFrame(dist)
                dd["what the shopper is thinking"] = dd["code"].map(S.voice)
                dd = dd[["what the shopper is thinking", "n", "share", "lift"]]
                dd.columns = ["what the shopper is thinking", "people",
                              "share of the group", "vs everyone else"]
                st.dataframe(dd, width="stretch", hide_index=True)
                st.caption(S.explain("lift"))
                st.info(
                    "**Read the lift with one caveat.** Segments are derived from the "
                    "classification: *not decided* is operationalised as the presence of "
                    "a Confidence-phase code, so Confidence codes cannot appear in three "
                    "of the six segments at all. Part of this lift is the derivation "
                    "rule, not a measurement. The opportunity ranking does not depend on "
                    "it — set the `segment fit` slider to zero and the order holds.",
                    icon="🔁")

        st.divider()
        st.markdown("**All segments, and the basis each was judged on**")
        r = rec.copy()
        r["segment"] = r["segment_id"].astype(int).astype(str) + " · " + r["segment_name"]
        st.dataframe(r[["segment", "n", "share", "basis", "rankable_cells",
                        "solvable_n", "score", "recommended"]],
                     width="stretch", hide_index=True)
        st.caption("`rankable_cells` is how many segment × code cells reach n ≥ 30. "
                   "`basis` records which matrix actually carried the judgement — a "
                   "directional read must never be quoted later as a ranked one.")
        st.caption("Segment ① Collectors is absent: it was removed from the addressable "
                   "population before this table was computed (AC-12).")

# ----------------------------------------------------------------- hypotheses
with tab_hyp:
    hyp = db.query("SELECT * FROM hypotheses")
    if hyp.empty:
        st.info("Hypotheses not generated yet.")
    else:
        st.caption(
            "A hypothesis is a causal claim with a kill condition. Every one below "
            "carries what would **disprove** it (AC-7) and what already **argues "
            "against** it — and the supporting count, source diversity and verbatims "
            "are computed from the classifications, never written by the model.")
        order = {"high": 0, "medium": 1, "low": 2}
        hyp = hyp.assign(_o=hyp["confidence"].map(order).fillna(3)).sort_values(
            ["_o", "supporting_n"], ascending=[True, False])
        for _, h in hyp.iterrows():
            codes = json.loads(h["codes"])
            fw = " + ".join(S.name(c) for c in codes)
            head, _, mech = str(h["statement"]).partition("\n\nMechanism: ")
            badge = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(h["confidence"], "⚪")
            with st.expander(f"{badge} **{h['hypothesis_id']}** · {fw} · "
                             f"n={int(h['supporting_n'])} · {h['confidence']} confidence"):
                st.markdown(f"**{head}**")
                if mech:
                    st.markdown(f"**Mechanism.** {mech}")
                st.markdown(f"**What would disprove it.** {h['falsifier']}")
                st.markdown(f"**What argues against it.** {h['contradicting']}")
                st.caption(f"{int(h['supporting_n'])} records across "
                           f"{int(h['source_diversity'] or 0)} sources.")
                vids = json.loads(h["verbatim_ids"] or "[]")
                if vids:
                    ph = ",".join("?" * len(vids))
                    q = db.query(
                        f"""SELECT DISTINCT cl.evidence_span, rec.source, rec.source_url
                            FROM classifications cl JOIN records rec
                              ON rec.record_id = cl.record_id
                            WHERE cl.record_id IN ({ph}) AND cl.span_verified = 1
                              AND rec.text_available = 1 LIMIT 4""", tuple(vids))
                    if not q.empty:
                        st.markdown("**In users' words**")
                        for _, v in q.iterrows():
                            st.markdown(f"> {v['evidence_span'].strip()}  \n"
                                        f"<sub>[{v['source']}]({v['source_url']})</sub>",
                                        unsafe_allow_html=True)
                        st.caption("Every quote is verified as an exact substring of the "
                                   "record it cites. A span that is not exact is not "
                                   "evidence and is never shown (T-6).")

# -------------------------------------------------------------------- insights
with tab_ins:
    ins = db.query("SELECT * FROM insights ORDER BY novelty DESC, insight_id")
    if ins.empty:
        st.info("Insights not generated yet.")
    else:
        novel = ins[ins["novelty"] == 1]
        st.subheader(f"Outside the pre-registered hypotheses — {len(novel)} of {len(ins)}")
        st.caption(
            "AC-6 exists because an engine that returns only its author's priors did not "
            "mine the corpus, it confirmed a belief at some expense. Each insight was "
            "embedded against all 28 pre-registered hypotheses (H1–H15 / DH1–DH13); the "
            "similarity line was **calibrated against a control set of deliberate "
            "restatements**, not chosen. The filter produced a shortlist of 10 — the "
            "verdicts below were then made by hand and are committed in "
            "`codebook/novelty_verdicts.yaml`, because similarity separates a "
            "methodological claim from a barrier hypothesis by form, not by content.")
        for _, i in novel.iterrows():
            with st.container(border=True):
                st.markdown(f"**{i['insight_id']}** · {i['kind']}  \n{i['statement']}")
                st.caption(f"So what: {i['so_what']}")
                st.caption(f"Nearest pre-registered hypothesis: {i['nearest_prior']} "
                           f"(similarity {float(i['nearest_similarity'] or 0):.3f}). "
                           f"{i['novelty_note']}")
        st.divider()
        st.markdown("**Everything else the corpus supports**")
        for _, i in ins[ins["novelty"] == 0].iterrows():
            with st.expander(f"{i['insight_id']} · {i['kind']} — {str(i['statement'])[:90]}…"):
                st.markdown(i["statement"])
                st.caption(f"So what: {i['so_what']}")
                st.caption(f"Cites: " + "; ".join(
                    f"`{c['table']}[{c['key']}]`" for c in json.loads(i["cites"])))
                if i["novelty_note"]:
                    st.caption(f"Novelty verdict: {i['novelty_note']}")
        st.info(
            "**Every insight cites a materialised analysis row, and every number in it "
            "was matched against that row before it was stored.** Insights that failed "
            "either check were rejected, given one repair attempt, and rejected again if "
            "they still failed — the rejection counts are in the gate report.", icon="🔍")

# ------------------------------------------------------------------- artefacts
with tab_art:
    from pathlib import Path
    ART = Path(__file__).resolve().parents[2] / "data" / "artifacts"
    st.caption(
        "Generated from the hypotheses above, so the primary research tests what the "
        "corpus actually raised rather than what was easy to ask. Deterministic "
        "templates — no model call — so they cannot introduce a claim the corpus does "
        "not carry.")
    files = [("interview_guide.md", "Interview guide", "5–6 interviews, 40 minutes. "
              "Every question names the hypothesis it is trying to kill."),
             ("survey_instrument.md", "Survey instrument", "Screener plus 12 items. The "
              "only instrument here that can measure a silent barrier."),
             ("problem_framing_canvas.md", "Problem-framing canvas", "Who, what is in the "
              "way, how confident, and what would change our mind.")]
    for fname, title, blurb in files:
        path = ART / fname
        if not path.exists():
            continue
        with st.expander(f"**{title}** — {blurb}"):
            text = path.read_text()
            st.download_button(f"Download {fname}", text, file_name=fname,
                               mime="text/markdown", key=f"dl_{fname}")
            st.markdown(text)
