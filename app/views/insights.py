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

# The pipeline stores these labels with their code ids attached, which is right
# for an audit trail and wrong for a page someone reads once.
PLAIN_BUCKET = {
    "corpus": "Everyone we heard from",
    "c9_no_live_intent": "Never meant to buy",
    "collectors": "Saving for reference",
    "addressable": "Actually winnable",
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

st.warning(S.PROXY_WARNING, icon="⚠️")

tab_opp, tab_sens, tab_seg, tab_hyp, tab_ins, tab_art = st.tabs(
    ["What to solve first", "How sure are we?", "Who to build for",
     "What would prove us wrong", "What we learned", "Take it to interviews"])

# ---------------------------------------------------------------- opportunity
with tab_opp:
    st.subheader("Who this is actually about")
    st.caption(
        "Two groups are counted and then set aside, because **they are not a conversion "
        "problem at all.** Some people never intended to buy — they save for reference, "
        "and \"converting\" them would mean optimising against the user. Others show no "
        "live intent at any point. Both are measured first, because how big they are is "
        "itself one of the findings; leaving them in would quietly inflate every number "
        "that follows.")
    cols = st.columns(4)
    for col, bucket in zip(cols, ["corpus", "c9_no_live_intent", "collectors", "addressable"]):
        if bucket in addr.index:
            r = addr.loc[bucket]
            col.metric(PLAIN_BUCKET.get(bucket, str(r["label"]).split(" — ")[0]),
                       f"{int(r['n']):,}", help=str(r["reason"]))
            col.caption(f"{float(r['share_of_corpus']):.0%} of everyone we heard from")
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
    st.caption("Barriers with fewer than 30 records are scored but never ranked — a handful "
               "of comments cannot settle which problem is bigger. They are listed below "
               "with their counts.")

    # A total bar says which barrier won and nothing about why. The score is a
    # mean of six stored components, so it can be taken apart -- and the useful
    # reading is almost always in the slices. This is what makes the price case
    # legible instead of surprising.
    st.markdown("#### What each score is made of")
    st.caption("Bar length is the score at **equal weights**; each colour is one "
               "component's contribution to it. Move the sliders above to change the "
               "ranking; this chart stays at equal weights so it reads as the baseline.")
    dec = ranked.head(8).copy()
    dec["display"] = dec["code"].map(S.chart_label)
    st.plotly_chart(
        charts.contribution(dec.iloc[::-1], "display",
                            {c: COMPONENT_LABEL[c] for c in COMPONENTS},
                            title="", height=430),
        width="stretch")

    # Robust to the WEIGHTS and robust to the LABELLING are different claims,
    # and the winner is only one of them. Both facts were already in the app,
    # three tabs apart; putting them together is the difference between a
    # report and a claim.
    if len(ranked):
        top_code = str(ranked.iloc[0]["code"])
        lead_k = db.query("SELECT kappa, verdict FROM analysis_gold_agreement "
                          "WHERE code = ? AND measurable = 1", (top_code,))
        if not lead_k.empty and str(lead_k.iloc[0]["verdict"]) != "reliable":
            st.warning(
                f"**Robust to the weights is not the same as robust to the labelling.** "
                f"“{S.voice(top_code)}” agrees with the human coder at "
                f"κ {float(lead_k.iloc[0]['kappa']):.2f} — *{lead_k.iloc[0]['verdict']}*, "
                "short of the 0.60 bar — on the hand-labelled records where agreement "
                "could be measured at all. Its **rank** survives a thousand reweightings; "
                "its **boundary** against neighbouring doubts does not yet survive a "
                "second reader. That is the first thing the interviews are for.",
                icon="⚖️")

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
                       "than a formality.", icon="⚖️")
        d = sens.copy()
        d["barrier"] = d["code"].map(S.voice)
        d = d[["barrier", "top_share", "top3_share", "mean_rank", "p05_rank", "p95_rank"]]
        d.columns = ["barrier", "held 1st place", "stayed in top 3",
                     "average rank", "best rank", "worst rank"]
        st.dataframe(d, width="stretch", hide_index=True)
        st.caption("**Best and worst rank** are where each barrier landed across a "
                   "thousand different weightings. A barrier whose best and worst are the "
                   "same number never moved at all, however the weights were set — which "
                   "is the strongest form this evidence can take.")

    st.caption(
        "This tab is about the weights behind the *barrier* ranking. The matching test "
        "for the *stage* choice — how far the quiet stages would have to be "
        "under-reported to overtake the leader — is on **Analysis**, next to the stage "
        "chart it defends.")

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
                    "directional — read it as a hint, not as a ranking.",
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
        st.markdown("**All five groups, compared on the four things that decided it**")
        st.caption(
            "Size alone would be a lazy answer. A group is worth targeting only if it is "
            "also **reachable without a discount** — the assignment forbids monetary "
            "remedies — **distinctive**, so a fix aimed at it is not merely a fix for "
            "everyone, and **evidenced well enough that the engine can say what "
            "specifically stops it.** That last one is the quiet disqualifier.")

        # Parsed out of the rationale the pipeline wrote rather than recomputed
        # here, so this table cannot disagree with the synthesis step about its
        # own recommendation.
        r = rec.copy()
        r["group"] = r["segment_id"].astype(int).map(
            lambda i: ("⭐ " if i == F.TARGET_SEGMENT else "") + str(
                rec.set_index("segment_id").loc[i, "segment_name"]))
        r["how big"] = r["n"].astype(int)
        r["% of winnable"] = r["share"].map(lambda v: f"{float(v):.1%}")
        r["fixable without a discount"] = r["rationale"].str.extract(
            r"(\d+)% of its coded barriers are solvable")[0].map(
            lambda v: f"{v}%" if pd.notna(v) else "—")
        r["sharpest barrier vs everyone"] = r["rationale"].str.extract(
            r"at ([\d.]+)x the corpus rate")[0].map(
            lambda v: f"{float(v):.1f}×" if pd.notna(v) else "—")
        r["barriers we can rank"] = r["rankable_cells"].astype(int)
        r["judged on"] = r["basis"]
        r["score"] = r["score"].map(lambda v: f"{float(v):.2f}")

        # Rendered as a static markdown table, NOT st.dataframe. Streamlit's
        # data grid measures its column widths when the element is laid out,
        # and inside a tab that is not the open one that measurement is zero:
        # every column collapses to a sliver and stays collapsed until the
        # viewer resizes the window, which no viewer does. A plain table has no
        # measurement step and cannot fail that way. Verified against a live
        # click-through of this tab, not just a local render.
        cols = ["group", "how big", "% of winnable", "fixable without a discount",
                "sharpest barrier vs everyone", "barriers we can rank", "judged on",
                "score"]
        md = ["| " + " | ".join(cols) + " |",
              "|" + "|".join(["---"] * len(cols)) + "|"]
        for _, row in r.iterrows():
            md.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
        st.markdown("\n".join(md))
        st.caption("`judged on` records which matrix actually carried the judgement — a "
                   "directional read must never be quoted later as a ranked one. "
                   "`barriers we can rank` is how many segment × barrier cells reach the "
                   "30-record floor.")

        st.warning(
            "**The chosen group does not win every column, and the honest reading "
            "matters.** Lapsed Intenders are far *sharper* — their most distinctive "
            "barrier runs at 11.4× the corpus rate against 2.2× for Stuck Deciders — so "
            "on distinctiveness alone they would lead. They lose because they are 78 "
            "people with **one** rankable barrier cell: the engine can say who they are "
            "and not what to build for them. Stuck Deciders win on the *combination* — "
            "the largest winnable group, wholly addressable without a discount, and the "
            "only one evidenced deeply enough to act on. A sharper group that cannot be "
            "acted on is a research lead, not a target, and it is carried into the "
            "interview guide as one.", icon="⚖️")
        st.caption("Segment ① Collectors is absent: it was removed from the addressable "
                   "group before this table was computed — they are not a conversion problem.")

# ----------------------------------------------------------------- hypotheses
with tab_hyp:
    hyp = db.query("SELECT * FROM hypotheses")
    if hyp.empty:
        st.info("Hypotheses not generated yet.")
    else:
        st.caption(
            "A hypothesis is a causal claim with a kill condition. Every one below "
            "carries what would **disprove** it and what already **argues "
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
                                   "evidence and is never shown.")

# -------------------------------------------------------------------- insights
with tab_ins:
    ins = db.query("SELECT * FROM insights ORDER BY novelty DESC, insight_id")
    if ins.empty:
        st.info("Insights not generated yet.")
    else:
        novel = ins[ins["novelty"] == 1]
        st.subheader(f"Outside the pre-registered hypotheses — {len(novel)} of {len(ins)}")
        st.caption(
            "An engine that returns only what its author already believed did not mine "
            "anything — it confirmed a hunch at some expense. So each insight was "
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
