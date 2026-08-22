"""Insights — what to do about it, argued in five steps.

WHY THIS PAGE LOOKS THE WAY IT DOES
-----------------------------------
Same correction as Analysis, for the same reason. This page held six tabs —
"What to solve first", "How sure are we?", "Who to build for", "What would
prove us wrong", "What we learned", "Take it to interviews" — which is a
faithful list of what it contains and not an argument. The recommendation sat
in tab one and everything that made it credible sat in tabs a reader never
opened, so the page asked for trust it had already earned somewhere else.

It is now one chain, numbered, each link a conclusion with one visual under it:

    1  892 of the 1,018 are actually winnable — and 126 are not a conversion
       problem at all, so they come out before anything is ranked
    2  one barrier leads on a score made of six visible parts
    3  it holds first place across a thousand different weightings   <- the test
    4  one group is worth building for, and it does not win every column
    5  eight hypotheses, each with the thing that would kill it

WHAT THIS PAGE MAY AND MAY NOT COMPUTE
--------------------------------------
No aggregation over raw records (architecture.md §4.2). The single exception,
unchanged: the opportunity SCORE is recomputed when a weight slider moves,
because the six components are stored as columns and re-weighting them is
arithmetic on numbers the pipeline already produced. Nothing is ever recounted.

WHY THE WEIGHTS ARE STILL SLIDERS
---------------------------------
A hard-coded ranking invites "why those weights?" and has no answer. A reader
who can move them and watch the order hold has been answered before asking. The
sliders now drive the DECOMPOSITION chart as well as the order, so one chart
shows what wins and why, and both move together.
"""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts, db, framework as F, story as S

MUTED = "#8a8a8a"
HAIR = "rgba(128,128,128,.28)"
OK, WARN, BAD = "#009E73", "#E69F00", "#D55E00"
ACCENT = "#CC79A7"

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
COMPONENT_LABEL = {
    "prevalence": "How often it comes up",
    "intensity": "How hard people work around it",
    "defer_share": "How often intent survives",
    "solvable_without_money": "Fixable without a discount",
    "evidence_strength": "How well-supported",
    "segment_fit": "How specific to the target group",
}


# --------------------------------------------------------------- furniture
def section(num: int, title: str, sub: str = "", colour: str = ACCENT) -> None:
    """A numbered link in the argument. The number is the point: it tells a
    reader where they are in a chain, which a bare heading cannot do."""
    st.html(
        f"<div style='margin:2.4rem 0 .5rem'>"
        f"<div style='display:flex;align-items:center;gap:.7rem'>"
        f"<span style='font-size:.68rem;font-weight:800;letter-spacing:.16em;"
        f"color:{colour}'>STEP {num}</span>"
        f"<span style='flex:1;height:2px;background:{colour};opacity:.3'></span></div>"
        f"<div style='font-size:1.5rem;font-weight:750;line-height:1.25;"
        f"margin:.4rem 0 .2rem'>{title}</div>"
        + (f"<div style='color:{MUTED};font-size:.93rem;line-height:1.55;"
           f"max-width:70ch'>{sub}</div>" if sub else "")
        + "</div>")


def verdict(text: str, colour: str) -> None:
    """The conclusion of a step. Skim only these five and you have the case."""
    st.html(
        f"<div style='border-left:4px solid {colour};padding:.6rem 0 .6rem .85rem;"
        f"margin:.9rem 0 .2rem;font-size:1.02rem;line-height:1.5'>{text}</div>")


def note(text: str) -> None:
    st.html(f"<div style='color:{MUTED};font-size:.82rem;line-height:1.5;"
            f"margin:.35rem 0 0;max-width:80ch'>{text}</div>")


def heading(text: str, top: str = "1.4rem") -> None:
    st.html(f"<div style='font-weight:700;margin:{top} 0 .1rem'>{text}</div>")


st.title("What to do about it")
st.html(f"<div style='color:{MUTED};font-size:1.02rem;margin:-.5rem 0 .4rem;"
        f"max-width:72ch;line-height:1.55'>Analysis picked the step of the journey. "
        f"This page picks the barrier and the group — and shows what would have to be "
        f"true for it to be wrong.</div>")

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
sens = db.query("SELECT * FROM analysis_weight_sensitivity ORDER BY top_share DESC")
rec = db.query("SELECT * FROM analysis_segment_recommendation ORDER BY score DESC")

n_corpus = int(addr.loc["corpus", "n"])
n_addr = int(addr.loc["addressable", "n"])
n_removed = n_corpus - n_addr
lead_row = opp[opp["rank"] == 1]
lead_code = str(lead_row["code"].iloc[0]) if not lead_row.empty else ""
winner = rec[rec["recommended"] == 1]

st.warning(S.PROXY_WARNING, icon="⚠️")

# ------------------------------------------------------------- the chain
# The whole recommendation in one strip, before the scroll asks for any
# commitment. Each card is a CONCLUSION; the page below proves each one.
top_hold = float(sens["top_share"].iloc[0]) if not sens.empty else None
n_draws = int(sens["n_draws"].iloc[0]) if not sens.empty else 0
hyp_n = int(db.query("SELECT count(*) AS n FROM hypotheses").iloc[0]["n"])

CHAIN = [
    (f"<b>{n_addr:,}</b> of {n_corpus:,} are<br>actually winnable",
     f"{n_removed} were never a conversion problem", "#0072B2"),
    (f"One barrier leads:<br><b>“{S.voice(lead_code)}”</b>" if lead_code else "One barrier leads",
     "on a score made of six visible parts", ACCENT),
    ("It survives<br><b>a thousand reweightings</b>",
     (f"first place in {top_hold:.1%} of {n_draws:,} draws" if top_hold is not None
      else "tested, not asserted"), OK),
    (f"Build for<br><b>{winner.iloc[0]['segment_name']}</b>" if not winner.empty
     else "Build for one group",
     (f"{int(winner.iloc[0]['n']):,} people, {float(winner.iloc[0]['share']):.0%} of the "
      f"winnable" if not winner.empty else ""), "#56B4E9"),
    (f"<b>{hyp_n} hypotheses</b>,<br>each with a kill condition",
     "what would prove this wrong", BAD),
]
cards = []
for i, (headline, foot, colour) in enumerate(CHAIN, 1):
    cards.append(
        f"<div style='flex:1;min-width:150px;border-top:4px solid {colour};"
        f"padding:.55rem .5rem .1rem 0'>"
        f"<div style='font-size:.64rem;letter-spacing:.12em;color:{MUTED};"
        f"font-weight:700'>{i}</div>"
        f"<div style='font-size:.95rem;line-height:1.35;margin:.15rem 0 .3rem'>{headline}</div>"
        f"<div style='font-size:.76rem;color:{MUTED};line-height:1.35'>{foot}</div></div>")
arrow = (f"<div style='align-self:center;color:{MUTED};font-size:1.4rem;"
         f"padding:0 .25rem'>&rsaquo;</div>")
st.html("<div style='display:flex;flex-wrap:wrap;gap:.25rem;margin:.8rem 0 .2rem'>"
        + arrow.join(cards) + "</div>")


# ============================================================== STEP 1
section(1, "Who this is actually about",
        "Some people save things they never intended to buy. “Converting” them would "
        "mean optimising against the user, so they are counted first — how many there "
        "are is itself a finding — and then taken out, before anything is ranked. "
        "Leaving them in would quietly inflate every number that follows.",
        "#0072B2")

# One bar, to scale, instead of four metric tiles. The subtraction IS the point
# of this step, and four numbers side by side do not show a subtraction.
fig = go.Figure()
for label, value, colour, tone in (
        ("Actually winnable", n_addr, "#0072B2", "white"),
        ("Not a conversion problem", n_removed, "#8C8C8C", "white")):
    fig.add_trace(go.Bar(
        x=[value], y=["corpus"], orientation="h", marker_color=colour,
        text=[f"<b>{label}</b><br>{value:,} · {value / n_corpus:.0%}"],
        textposition="inside", insidetextanchor="middle", textangle=0,
        textfont=dict(color=tone),
        hovertemplate=f"<b>{label}</b><br>{value:,} records<extra></extra>"))
fig.update_layout(
    barmode="stack", height=110, showlegend=False,
    margin=dict(l=6, r=6, t=6, b=6), plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)", xaxis=dict(visible=False),
    yaxis=dict(visible=False), uniformtext=dict(mode="hide", minsize=9))
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

cols = st.columns(2)
for col, bucket, title in ((cols[0], "collectors", "Saving for reference"),
                           (cols[1], "c9_no_live_intent", "Never meant to buy")):
    if bucket in addr.index:
        r = addr.loc[bucket]
        col.html(
            f"<div style='border:1px solid {HAIR};border-radius:7px;padding:.7rem .85rem'>"
            f"<div style='font-size:1.4rem;font-weight:750;line-height:1'>"
            f"{int(r['n']):,}</div>"
            f"<div style='font-weight:650;font-size:.92rem;margin-top:.2rem'>{title}</div>"
            f"<div style='font-size:.79rem;color:{MUTED};line-height:1.4;margin-top:.2rem'>"
            f"{float(r['share_of_corpus']):.1%} of everyone we heard from</div></div>")

overlap = int(addr.loc["overlap", "n"]) if "overlap" in addr.index else 0
note(f"The two rules overlap by {overlap}, so they are not additive — "
     f"{n_removed} records come out in total, not "
     f"{int(addr.loc['collectors', 'n']) + int(addr.loc['c9_no_live_intent', 'n'])}.")
verdict(f"Everything below is scored over <b>{n_addr:,} people</b>, not {n_corpus:,}. "
        f"Shares on this page and shares on Analysis therefore have different "
        f"denominators <i>on purpose</i>.", "#0072B2")


# ============================================================== STEP 2
section(2, "What to solve first",
        "Six things decide whether a barrier is worth attacking: how often it comes "
        "up, how hard people work around it, whether the intent survives it, whether "
        "it can be fixed without a discount, how well-evidenced it is, and how "
        "specific it is to the group we care about. Every bar below is those six "
        "stacked — so the bar says which wins, and the colours say why.")

heading("Move the weights. The ranking should not need your agreement to survive.",
        top=".2rem")
note("Nothing is recounted when a slider moves — the six stored components are "
     "re-weighted. Both the order and the colour slices below respond.")

wcols = st.columns(3)
weights = {}
for i, comp in enumerate(COMPONENTS):
    weights[comp] = wcols[i % 3].slider(
        COMPONENT_LABEL[comp], 0.0, 2.0, 1.0, 0.05, help=COMPONENT_HELP[comp])

total_w = sum(weights.values()) or 1.0
opp["live_score"] = sum(opp[c] * weights[c] for c in COMPONENTS) / total_w

ranked = opp[(opp["excluded"] == 0) & (opp["rank"].notna())].copy()
ranked = ranked.sort_values("live_score", ascending=False).reset_index(drop=True)
ranked["live_rank"] = ranked.index + 1

if len(ranked) and lead_code and str(ranked.iloc[0]["code"]) != lead_code:
    st.error(f"**At these weights the answer changes** — from “{S.voice(lead_code)}” "
             f"to “{S.voice(str(ranked.iloc[0]['code']))}”. That is a finding, not a "
             f"malfunction: it means the ranking depends on a judgement you have just "
             f"disagreed with.", icon="↕️")

dec = ranked.head(9).copy()
dec["display"] = dec["code"].map(S.chart_label)
st.plotly_chart(
    charts.contribution(dec.iloc[::-1], "display",
                        {c: COMPONENT_LABEL[c] for c in COMPONENTS},
                        title="", height=440, weights=weights),
    width="stretch")
note("Bar length is the score at the weights you have set; each colour is one "
     "component's contribution to it. Barriers under 30 records are scored but never "
     "ranked — a handful of comments cannot settle which problem is bigger.")

# Robust to the WEIGHTS and robust to the LABELLING are different claims, and
# the winner is only one of them. Both facts were already in the app, three tabs
# apart; putting them together is the difference between a report and a claim.
if len(ranked):
    top_code = str(ranked.iloc[0]["code"])
    lead_k = db.query("SELECT kappa, verdict FROM analysis_gold_agreement "
                      "WHERE code = ? AND measurable = 1", (top_code,))
    if not lead_k.empty and str(lead_k.iloc[0]["verdict"]) != "reliable":
        st.warning(
            f"**Robust to the weights is not the same as robust to the labelling.** "
            f"“{S.voice(top_code)}” agrees with the human coder at "
            f"κ {float(lead_k.iloc[0]['kappa']):.2f} — *{lead_k.iloc[0]['verdict']}*, "
            "short of the 0.60 bar. Its **rank** survives a thousand reweightings; its "
            "**boundary** against neighbouring doubts does not yet survive a second "
            "reader. That is the first thing the interviews are for.", icon="⚖️")

# The numbers in this callout are read from the stored components rather than
# asserted: an earlier draft said price scored "near zero" on solvability when
# it actually scores 0.50, which the chart directly above would have contradicted.
price = opp[opp["code"] == "C6"]
if not price.empty:
    pr = price.iloc[0]
    st.info(
        f"**Price ranks 8th here against 2nd on size alone, and that is the constraint "
        f"doing its job.** It scores **{float(pr['prevalence']):.2f} on how often it "
        f"comes up** — near the top — but only **{float(pr['solvable_without_money']):.2f} "
        f"on *fixable without a discount*, because the assignment forbids monetary "
        f"remedies, and **{float(pr['segment_fit']):.2f} on *how specific to the target "
        f"group*, because the people it stops are Waiters rather than Stuck Deciders. "
        f"Two low slices on a six-part score are enough to move it down six places. "
        f"That is a statement about what this project is allowed to build, not a claim "
        f"that price does not matter — it has to be resolved into transparency, "
        f"anchoring and timing, or reported as out of scope.", icon="💰")

# The precise table, under the picture rather than instead of it. This is also
# the element `test_the_weight_sliders_are_live` reads, so it must stay a real
# dataframe and must stay the FIRST one on the page.
with st.expander("The same ranking as numbers, with every component"):
    show = ranked.copy()
    show["what the shopper is thinking"] = show["code"].map(S.voice)
    tbl = show[["live_rank", "what the shopper is thinking", "n", "live_score"] + COMPONENTS]
    tbl.columns = (["#", "what the shopper is thinking", "records", "score"]
                   + [COMPONENT_LABEL[c] for c in COMPONENTS])
    st.dataframe(tbl, width="stretch", hide_index=True,
                 column_config={c: st.column_config.ProgressColumn(
                     c, min_value=0.0, max_value=1.0, format="%.2f")
                     for c in ["score"] + [COMPONENT_LABEL[c] for c in COMPONENTS]})

# "the only one that is large AND fixable" was overclaiming: C1 is also large
# and also scores 1.0 on solvability. It wins on the full six, not on two.
verdict(f"The barrier to solve first is <b>“{S.voice(lead_code)}”</b> — the biggest "
        f"single barrier in the corpus at {int(lead_row['n'].iloc[0]):,} records, "
        f"fixable without touching the price, and top or near-top on every one of the "
        f"other four components." if lead_code else "", ACCENT)


# ============================================================== STEP 3
section(3, "How sure are we?",
        "A ranking asserted once is worth very little. So the weights were perturbed "
        "a thousand times — every component nudged by up to ±30% — and the ranking was "
        "recomputed each time. The bars below are where each barrier LANDED across all "
        "of those runs — the band each one stayed inside 90% of the time.", OK)

if sens.empty:
    st.info("Sensitivity not computed.")
else:
    top = sens.iloc[0]
    st.html(
        f"<div style='display:flex;flex-wrap:wrap;gap:.5rem;margin:.4rem 0 1rem'>"
        f"<div style='flex:1;min-width:230px;border:1px solid {HAIR};border-radius:7px;"
        f"padding:.75rem .9rem'>"
        f"<div style='font-size:2rem;font-weight:750;line-height:1;color:{OK}'>"
        f"{float(top['top_share']):.1%}</div>"
        f"<div style='font-size:.88rem;margin-top:.25rem'>of "
        f"{int(top['n_draws']):,} reweightings still put "
        f"<b>“{S.voice(str(top['code']))}”</b> first</div></div>"
        f"<div style='flex:1;min-width:230px;border:1px solid {HAIR};border-radius:7px;"
        f"padding:.75rem .9rem'>"
        f"<div style='font-size:2rem;font-weight:750;line-height:1'>±30%</div>"
        f"<div style='font-size:.88rem;margin-top:.25rem'>how far every weight was "
        f"pushed, in both directions, on each of those draws</div></div></div>")

    d = sens.copy()
    d["label"] = d["code"].map(S.chart_label)
    d = d.sort_values("mean_rank", ascending=False)
    d["span"] = d["p95_rank"] - d["p05_rank"]
    d["fixed"] = d["span"] == 0

    fig = go.Figure()
    # The bar runs from the 5th to the 95th percentile rank, so it starts AT
    # p05 rather than half a rank before it — an earlier version offset both
    # ends by -0.5 and the mean marker sat outside its own band.
    #
    # A zero-width band gets a visible marker rather than a bar of no width
    # that silently disappears, because "it did not move" is the strongest
    # result this evidence can produce and must not be the invisible one.
    fig.add_trace(go.Bar(
        x=d["span"], base=d["p05_rank"], y=d["label"], orientation="h",
        marker_color=[OK if f else charts.PALETTE[0] for f in d["fixed"]],
        opacity=0.45, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=d["mean_rank"], y=d["label"], mode="markers", showlegend=False,
        marker=dict(size=11, color=[OK if f else charts.PALETTE[0] for f in d["fixed"]],
                    line=dict(width=0)),
        text=[(f"rank {int(a)} in 90% of draws" if f
               else f"ranks {int(a)}–{int(b)} in 90% of draws")
              for f, a, b in zip(d["fixed"], d["p05_rank"], d["p95_rank"])],
        hovertemplate="<b>%{y}</b><br>average rank %{x:.1f}<br>%{text}<extra></extra>"))
    fig.update_layout(
        height=110 + 30 * len(d), margin=dict(l=10, r=20, t=10, b=34),
        plot_bgcolor="rgba(0,0,0,0)", bargap=0.55,
        xaxis=dict(title="rank across 1,000 reweightings (1 is best)",
                   title_font_size=11, showgrid=True, gridcolor=HAIR,
                   dtick=1, range=[0.4, float(d["p95_rank"].max()) + 0.6]),
        yaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch")
    note("Each bar spans the <b>5th to the 95th percentile</b> of where that barrier "
         "landed — the band it stayed inside on 90% of the draws — and the dot is its "
         "average rank. A bare dot means the same rank on essentially every draw, "
         "however the weights were set. That is the strongest form this evidence can "
         "take, and most of this ranking has it.")

    if float(top["top_share"]) >= 0.75:
        verdict("The order is not an artefact of the weights we happened to choose. "
                "It survives essentially any reasonable disagreement about them — "
                "which is a far stronger claim than a single asserted ranking.", OK)
    else:
        verdict("The top two cannot be separated on this evidence. The honest headline "
                "is a tie, and the interviews are the tiebreak rather than a "
                "formality.", WARN)

note("This is the test for the <b>barrier</b> ranking. The matching test for the "
     "<b>step</b> of the journey — how far the quiet steps would have to be "
     "under-reported to overtake the leader — is on <b>Analysis</b>, beside the chart "
     "it defends.")


# ============================================================== STEP 4
section(4, "Who to build for",
        "Size alone would be a lazy answer. A group is worth targeting only if it is "
        "also reachable without a discount, distinctive enough that a fix aimed at it "
        "is not merely a fix for everyone, and evidenced deeply enough that the engine "
        "can say what specifically stops it. That last one is the quiet disqualifier.",
        "#56B4E9")

if rec.empty:
    st.info("Segment recommendation not computed.")
else:
    r = rec.copy()
    r["group"] = r["segment_name"].astype(str)
    # Parsed out of the rationale the pipeline wrote rather than recomputed here,
    # so this cannot disagree with the synthesis step about its own recommendation.
    r["solvable"] = pd.to_numeric(
        r["rationale"].str.extract(r"(\d+)% of its coded barriers are solvable")[0],
        errors="coerce")
    r["sharpest"] = pd.to_numeric(
        r["rationale"].str.extract(r"at ([\d.]+)x the corpus rate")[0], errors="coerce")
    r["cells"] = r["rankable_cells"].astype(int)
    r["pct"] = r["share"].astype(float) * 100
    target = int(F.TARGET_SEGMENT)

    # Four small multiples rather than one eight-column table. The argument here
    # is "wins on the combination, not on any single column", and four charts
    # side by side make that readable in one pass where a table does not.
    TESTS = [
        ("How big", "pct", "% of the winnable population", "{:.0f}%"),
        ("Fixable without a discount", "solvable", "% of its barriers", "{:.0f}%"),
        ("How distinctive", "sharpest", "× the corpus rate, sharpest barrier", "{:.1f}×"),
        ("Can we say what to build?", "cells", "barrier cells with enough evidence", "{:.0f}"),
    ]
    # ONE order for all four charts, fixed here. Sorting each chart by its own
    # field put the groups in four different orders under a single column of
    # labels, so a reader tracing "Stuck Deciders" across the row read its size
    # off chart one and Lapsed Intenders' 11.4x distinctiveness off chart three.
    # Ascending because Plotly draws the first horizontal bar at the bottom.
    dd = r.sort_values("pct", ascending=True)
    colours = ["#56B4E9" if int(sid) == target else "#BBBBBB"
               for sid in dd["segment_id"]]
    for col, (title, field, axis, fmt) in zip(st.columns(4), TESTS):
        fig = go.Figure(go.Bar(
            x=dd[field], y=dd["group"], orientation="h", marker_color=colours,
            text=[fmt.format(v) if pd.notna(v) else "—" for v in dd[field]],
            textposition="outside", cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x}<extra></extra>"))
        fig.update_layout(
            height=250, margin=dict(l=4, r=8, t=42, b=30),
            title=dict(text=title, font=dict(size=12.5), x=0, xanchor="left"),
            plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
            xaxis=dict(visible=False,
                       range=[0, float(dd[field].max() or 1) * 1.35]),
            yaxis=dict(showgrid=False, showticklabels=field == "pct",
                       tickfont=dict(size=10.5)))
        col.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    note("Highlighted bar is the recommended group. Group names appear once, on the "
         "left chart — every chart uses that same row order, so you can read straight "
         "across. Stuck Deciders are top or joint-top on three of the four, and last "
         "on the fourth.")

    if not winner.empty:
        w = winner.iloc[0]
        st.success(str(w["rationale"]), icon="🎯")
        if str(w["basis"]) != "segment x code":
            st.warning(
                "This rests on **segment × stage**, not segment × code — too few code "
                "cells reach n ≥ 30. Code-level detail for this segment is "
                "directional: read it as a hint, not as a ranking.", icon="⚠️")

        dist = json.loads(w["distinctive"] or "[]")
        if dist:
            heading("What makes this group distinctive, not merely large")
            dd = pd.DataFrame(dist).sort_values("lift")
            dd["label"] = dd["code"].map(S.voice)
            fig = go.Figure(go.Bar(
                x=dd["lift"], y=dd["label"], orientation="h",
                marker_color="#56B4E9",
                text=[f" {v:.1f}× · {int(n)} people" for v, n in zip(dd["lift"], dd["n"])],
                textposition="outside", cliponaxis=False,
                hovertemplate="<b>%{y}</b><br>%{x:.2f}× the corpus rate<extra></extra>"))
            fig.add_vline(x=1.0, line_dash="dash", line_color=MUTED, line_width=1.5,
                          annotation_text="1× — as common as everywhere else",
                          annotation_position="top", annotation_font_size=10.5)
            fig.update_layout(
                height=110 + 34 * len(dd), margin=dict(l=10, r=10, t=34, b=26),
                plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
                xaxis=dict(range=[0, float(dd["lift"].max()) * 1.55], showgrid=False,
                           title="× more common than in the corpus overall",
                           title_font_size=11),
                yaxis=dict(showgrid=False))
            st.plotly_chart(fig, width="stretch")
            st.info(
                "**Read the lift with one caveat.** Segments are derived from the "
                "classification: *not decided* is operationalised as the presence of a "
                "Confidence-phase code, so those codes cannot appear in three of the six "
                "groups at all. Part of this lift is the derivation rule, not a "
                "measurement. The barrier ranking does not depend on it — set the "
                "*How specific to the target group* slider to zero and the order holds.",
                icon="🔁")

    st.warning(
        "**The chosen group does not win every column, and the honest reading matters.** "
        "Lapsed Intenders are far *sharper* — their most distinctive barrier runs at "
        "11.4× the corpus rate against 2.2× for Stuck Deciders — so on distinctiveness "
        "alone they would lead. They lose because they are 78 people with **one** "
        "rankable barrier cell: the engine can say who they are and not what to build "
        "for them. Stuck Deciders win on the *combination* — the largest winnable "
        "group, wholly addressable without a discount, and the only one evidenced "
        "deeply enough to act on. A sharper group that cannot be acted on is a research "
        "lead, not a target, and it is carried into the interview guide as one.",
        icon="⚖️")
    note("Collectors are absent from these four charts: they were removed in step 1 "
         "before any of this was computed. They are not a conversion problem.")


# ============================================================== STEP 5
section(5, "What would prove us wrong",
        "A claim that cannot fail is not a finding. Each hypothesis below is a causal "
        "claim with a stated kill condition — the observation that would end it — plus "
        "what already argues against it. The counts and quotes come from the "
        "classifications; only the wording is the model's.", BAD)

hyp = db.query("SELECT * FROM hypotheses")
if hyp.empty:
    st.info("Hypotheses not generated yet.")
else:
    order = {"high": 0, "medium": 1, "low": 2}
    hyp = hyp.assign(_o=hyp["confidence"].map(order).fillna(3)).sort_values(
        ["_o", "supporting_n"], ascending=[True, False]).reset_index(drop=True)

    # One quote per hypothesis, fetched in a single query rather than one per
    # card. A verified verbatim on the card is worth more than a verified
    # verbatim behind a click nobody makes.
    first_ids = {}
    for _, h in hyp.iterrows():
        vids = json.loads(h["verbatim_ids"] or "[]")
        if vids:
            first_ids[str(h["hypothesis_id"])] = vids[:3]
    flat = sorted({v for vs in first_ids.values() for v in vs})
    spans = {}
    if flat:
        ph = ",".join("?" * len(flat))
        q = db.query(
            f"""SELECT cl.record_id, cl.evidence_span FROM classifications cl
                JOIN records rec ON rec.record_id = cl.record_id
                WHERE cl.record_id IN ({ph}) AND cl.span_verified = 1
                  AND rec.text_available = 1""", tuple(flat))
        for _, v in q.iterrows():
            spans.setdefault(str(v["record_id"]), str(v["evidence_span"]).strip())

    BADGE = {"high": (OK, "well evidenced"), "medium": (WARN, "moderately evidenced"),
             "low": (BAD, "thin — treat as a lead")}
    rows = list(hyp.iterrows())
    for start in range(0, len(rows), 2):
        for col, (_, h) in zip(st.columns(2), rows[start:start + 2]):
            codes = json.loads(h["codes"])
            head, _, mech = str(h["statement"]).partition("\n\nMechanism: ")
            bcol, btext = BADGE.get(str(h["confidence"]), (MUTED, str(h["confidence"])))
            quote = ""
            for vid in first_ids.get(str(h["hypothesis_id"]), []):
                if vid in spans:
                    quote = spans[vid]
                    break
            qhtml = (f"<div style='border-left:2px solid {HAIR};padding-left:.6rem;"
                     f"margin-top:.55rem;font-size:.8rem;color:{MUTED};font-style:italic;"
                     f"line-height:1.4'>“{quote[:190]}”</div>" if quote else "")
            col.html(
                f"<div style='border:1px solid {HAIR};border-radius:7px;"
                f"padding:.8rem .9rem;height:100%;min-height:300px'>"
                f"<div style='display:flex;justify-content:space-between;"
                f"align-items:baseline;gap:.5rem'>"
                f"<span style='font-size:.7rem;font-weight:700;letter-spacing:.1em;"
                f"color:{bcol}'>● {btext.upper()}</span>"
                f"<span style='font-size:.72rem;color:{MUTED}'>"
                f"{int(h['supporting_n'])} records · {int(h['source_diversity'] or 0)} "
                f"sources</span></div>"
                f"<div style='font-weight:650;font-size:.95rem;line-height:1.4;"
                f"margin:.4rem 0 .3rem'>{head}</div>"
                + (f"<div style='font-size:.81rem;color:{MUTED};line-height:1.45'>"
                   f"{mech}</div>" if mech else "")
                + f"<div style='margin-top:.6rem;font-size:.82rem;line-height:1.45'>"
                f"<span style='color:{BAD};font-weight:700'>Killed by:</span> "
                f"{h['falsifier']}</div>"
                + qhtml + "</div>")

# What the engine found that nobody told it to look for. This is the answer to
# "did it mine anything, or confirm a hunch at some expense?", so it belongs in
# the argument rather than in an appendix.
ins = db.query("SELECT * FROM insights ORDER BY novelty DESC, insight_id")
if not ins.empty:
    novel = ins[ins["novelty"] == 1]
    heading(f"And {len(novel)} things nobody asked it to look for", top="2rem")
    note("Every insight was embedded against all 28 pre-registered hypotheses, with the "
         "similarity line <b>calibrated against a control set of deliberate "
         "restatements</b> rather than chosen. The filter produced a shortlist; these "
         "verdicts were then made by hand, because similarity separates a "
         "methodological claim from a barrier hypothesis by form, not by content.")
    for start in range(0, len(novel), 2):
        for col, (_, i) in zip(st.columns(2), list(novel.iterrows())[start:start + 2]):
            col.html(
                f"<div style='border:1px solid {HAIR};border-radius:7px;"
                f"padding:.75rem .9rem;height:100%;min-height:190px'>"
                f"<div style='font-size:.68rem;letter-spacing:.1em;color:{ACCENT};"
                f"font-weight:700'>{str(i['kind']).upper()}</div>"
                f"<div style='font-size:.9rem;line-height:1.45;margin:.35rem 0 .4rem'>"
                f"{i['statement']}</div>"
                f"<div style='font-size:.8rem;color:{MUTED};line-height:1.4'>"
                f"<b>So what:</b> {i['so_what']}</div></div>")


# ========================================================== what happens next
st.html(f"<div style='margin:2.6rem 0 .4rem'><div style='height:1px;background:{HAIR}'>"
        f"</div><div style='font-size:1.15rem;font-weight:700;margin-top:1rem'>"
        f"Take it to the interviews</div>"
        f"<div style='color:{MUTED};font-size:.9rem;max-width:70ch;line-height:1.5'>"
        f"Generated from the hypotheses above, so the primary research tests what the "
        f"corpus actually raised rather than what was easy to ask. Deterministic "
        f"templates — no model call — so they cannot introduce a claim the corpus does "
        f"not carry.</div></div>")

ART = Path(__file__).resolve().parents[2] / "data" / "artifacts"
FILES = [("interview_guide.md", "Interview guide",
          "5–6 interviews, 40 minutes. Every question names the hypothesis it is "
          "trying to kill."),
         ("survey_instrument.md", "Survey instrument",
          "Screener plus 12 items. The only instrument here that can measure a "
          "silent barrier."),
         ("problem_framing_canvas.md", "Problem-framing canvas",
          "Who, what is in the way, how confident, and what would change our mind.")]
acols = st.columns(3)
for col, (fname, title, blurb) in zip(acols, FILES):
    path = ART / fname
    if not path.exists():
        continue
    with col:
        st.html(f"<div style='font-weight:700;font-size:.98rem'>{title}</div>"
                f"<div style='font-size:.82rem;color:{MUTED};line-height:1.45;"
                f"margin:.2rem 0 .5rem;min-height:3.4em'>{blurb}</div>")
        st.download_button(f"Download {fname}", path.read_text(), file_name=fname,
                           mime="text/markdown", key=f"dl_{fname}", width="stretch")
for fname, title, _ in FILES:
    path = ART / fname
    if path.exists():
        with st.expander(f"Read {title.lower()} here"):
            st.markdown(path.read_text())


# ============================================================== the checks
st.html(f"<div style='margin:2.6rem 0 .4rem'><div style='height:1px;background:{HAIR}'>"
        f"</div><div style='font-size:1.15rem;font-weight:700;margin-top:1rem'>"
        f"If you want to attack this</div>"
        f"<div style='color:{MUTED};font-size:.9rem;max-width:70ch;line-height:1.5'>"
        f"The caveats that bind every number above, carried from the pipeline rather "
        f"than written here — so they cannot drift from what the analysis actually "
        f"did.</div></div>")

flags = db.query("SELECT flag_id, scope, applies_to, severity, statement, basis "
                 "FROM analysis_method_flags "
                 "ORDER BY CASE severity WHEN 'binding' THEN 0 ELSE 1 END, flag_id")
if not flags.empty:
    for _, f in flags.iterrows():
        binding = str(f["severity"]) == "binding"
        col = BAD if binding else WARN
        # The statements are printed verbatim so they cannot drift from what the
        # pipeline recorded — which means they carry raw code ids, against this
        # app's rule that the plain name leads. Resolved by naming the barrier
        # first rather than by rewriting the statement.
        lead_in = ""
        if str(f["scope"]) == "code":
            try:
                codes = [c for c in json.loads(f["applies_to"] or "[]") if S.voice(c)]
            except (ValueError, TypeError):
                codes = []
            if codes:
                lead_in = ("<b>" + " · ".join(f"“{S.voice(c)}”" for c in codes)
                           + "</b><br>")
        st.html(
            f"<div style='display:flex;gap:.7rem;margin:.5rem 0;align-items:flex-start'>"
            f"<span style='flex:0 0 auto;font-size:.62rem;font-weight:800;"
            f"letter-spacing:.1em;color:{col};border:1px solid {col};border-radius:3px;"
            f"padding:.1rem .35rem;margin-top:.15rem'>"
            f"{str(f['severity']).upper()}</span>"
            f"<span style='font-size:.86rem;line-height:1.5'>{lead_in}{f['statement']}"
            f"<span style='color:{MUTED};font-size:.76rem'> — {f['basis']}</span>"
            f"</span></div>")

with st.expander("Scored but not ranked — every barrier that did not make the cut"):
    excl = opp[(opp["excluded"] == 1) | (opp["rank"].isna())].copy()
    if excl.empty:
        st.info("Every scored barrier is ranked.")
    else:
        excl["voice"] = excl["code"].map(S.voice)
        lines = ["| barrier | records | why it is not ranked |", "|---|---|---|"]
        for _, e in excl.sort_values("n", ascending=False).iterrows():
            lines.append(f"| “{e['voice']}” | {int(e['n'])} | {e['exclusion_reason']} |")
        st.markdown("\n".join(lines))

with st.expander("Everything else the corpus supports, beyond the five above"):
    if not ins.empty:
        for _, i in ins[ins["novelty"] == 0].iterrows():
            st.markdown(f"**{i['insight_id']} · {i['kind']}** — {i['statement']}")
            st.caption(f"So what: {i['so_what']} · cites " + "; ".join(
                f"`{c['table']}[{c['key']}]`" for c in json.loads(i["cites"])))
    note("Every insight cites a materialised analysis row, and every number in it was "
         "matched against that row before it was stored. Insights that failed either "
         "check were rejected, given one repair attempt, and rejected again if they "
         "still failed — the rejection counts are in the P3 gate report on Analysis.")
