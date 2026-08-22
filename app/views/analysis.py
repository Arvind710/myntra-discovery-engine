"""Analysis — one argument, told in five steps, drawn rather than written.

WHY THIS PAGE LOOKS THE WAY IT DOES
-----------------------------------
Three shapes preceded this one. First a ranked list of code ids ("C2 · 241 ·
0.237"), legible to whoever wrote the codebook and to nobody else. Then the
journey model with the codes underneath it, which fixed the vocabulary but
buried the argument in four tabs — a reader who never clicked "How we know
this" never learned that the conclusion had been tested. Then that same page
with more prose on it, which is where Arvind stopped it: *nobody has time to
read this much; show them the analysis.*

So the organising idea here is no longer "sections about the data". It is a
CHAIN OF REASONING, numbered, that a stranger can follow top to bottom:

    1  a saved item has to survive four steps
    2  almost all the conversation is about one of them
    3  ... and that is not merely because the other three are quiet   <- the test
    4  inside that step, a handful of barriers carry the weight
    5  and those barriers concentrate in one group of shoppers

Every link in that chain gets ONE visual and ONE sentence of conclusion. The
chain is also summarised as a strip at the top, so a reader with sixty seconds
gets the whole argument before deciding which link to interrogate.

THREE RULES THIS PAGE KEEPS
---------------------------
1. NO AGGREGATION over raw records (architecture.md §4.2). Every figure is a
   SELECT from a materialised `analysis_*` table. The one exception is the
   segment tree, which sums six stored segment counts into its branches —
   arithmetic on numbers the pipeline already produced, not a recount.
2. THE MATHS IS DRAWN, NOT DESCRIBED. The inversion threshold, the
   reliability check and the co-occurrence lift were all prose here. A number
   that lives only in a caption is the number a reader skips.
3. RAW HTML GOES THROUGH `st.html`. `st.markdown(unsafe_allow_html=True)` in
   Streamlit 1.61 strips nested markup and renders an empty box, silently.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts, db, framework as F, story as S

MUTED = "#8a8a8a"
HAIR = "rgba(128,128,128,.28)"
OK, WARN, BAD = "#009E73", "#E69F00", "#D55E00"

# Verdicts from `analysis_gold_agreement`, mapped to something a reader who has
# never met Cohen's kappa can act on. The wording is deliberately about what to
# DO with the number, not what the number is.
RELIABILITY = {
    "reliable":       (OK,    "human coder agrees"),
    "weak":           (WARN,  "human agrees less often"),
    "unreliable":     (BAD,   "human disagreed — a lead, not a finding"),
    "not measurable": (MUTED, "too few hand labels to check"),
}


# --------------------------------------------------------------- furniture
def section(num: int, title: str, sub: str = "", colour: str = "#0072B2") -> None:
    """A numbered step in the argument. The number is the point: it tells a
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
    """The conclusion of a step. One sentence, on a coloured left rule, so the
    reader can skim only these five and still have the whole argument."""
    st.html(
        f"<div style='border-left:4px solid {colour};padding:.6rem 0 .6rem .85rem;"
        f"margin:.9rem 0 .2rem;font-size:1.02rem;line-height:1.5'>{text}</div>")


def note(text: str) -> None:
    st.html(f"<div style='color:{MUTED};font-size:.82rem;line-height:1.5;"
            f"margin:.35rem 0 0;max-width:80ch'>{text}</div>")


st.title("Where the journey breaks")
st.html(f"<div style='color:{MUTED};font-size:1.02rem;margin:-.5rem 0 .4rem;"
        f"max-width:72ch;line-height:1.55'>Five steps, in order. Each one is a "
        f"chart and a conclusion — the reasoning that takes 12,002 public posts "
        f"down to one step of the journey and one group of shoppers.</div>")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

prev = db.query("SELECT * FROM analysis_code_prevalence ORDER BY n DESC")
if prev.empty:
    st.info("Classification has not run yet."); st.stop()

denom = int(prev["denominator"].iloc[0])
prev["stage"] = prev["code"].map(S.stage_of)

stage_n = db.query("SELECT stage, sum(n) AS n FROM analysis_stage_outcome GROUP BY stage")
stage_n = {r["stage"]: int(r["n"]) for _, r in stage_n.iterrows()}
band_total = sum(stage_n.get(s, 0) for s in S.STAGE_ORDER) or 1

inv = db.query("SELECT * FROM analysis_stage_inversion ORDER BY n DESC")
seg = db.query("""SELECT segment_id, segment_name, count(*) AS n FROM segments_v2
                  GROUP BY segment_id, segment_name ORDER BY segment_id""")
rel = db.query("SELECT code, kappa, verdict, measurable FROM analysis_gold_agreement")
rel_by_code = {r["code"]: r for _, r in rel.iterrows()} if not rel.empty else {}

lead = max(S.STAGE_ORDER, key=lambda s: stage_n.get(s, 0))
lead_share = stage_n.get(lead, 0) / band_total
c_barriers = prev[(prev["stage"] == lead) & (prev["n"] >= charts.MIN_N_RANKED)]
tightest = None
if not inv.empty and inv["inversion_factor"].notna().any():
    tightest = inv[inv["inversion_factor"].notna()].sort_values("inversion_factor").iloc[0]
seg_by_id = {int(r["segment_id"]): int(r["n"]) for _, r in seg.iterrows()} if not seg.empty else {}
target_n = seg_by_id.get(F.TARGET_SEGMENT, 0)

st.warning(S.PROXY_WARNING, icon="⚠️")

# ------------------------------------------------------------- the chain
# The whole argument in one strip. This exists because the page below is a
# scroll, and a scroll asks for a commitment before it says what it is for.
# Each card is a CONCLUSION, not a topic heading — a reader who reads only
# these five has the finding and knows what was done to earn it.
CHAIN = [
    ("A saved item must survive<br><b>four steps</b>", "before it is bought",
     S.STAGE_COLOUR["A"]),
    (f"<b>{lead_share:.0%}</b> of the talk is about<br>one of them: "
     f"<b>{S.stage_title(lead)}</b>", f"{stage_n.get(lead, 0):,} records",
     S.STAGE_COLOUR["C"]),
    ("And it is not just the<br><b>loudest</b> step",
     (f"the quietest would need {float(tightest['inversion_factor']):.1f}× more "
      f"hidden records to overtake it" if tightest is not None else "tested, not assumed"),
     BAD),
    (f"Inside it, <b>{len(c_barriers)} barriers</b><br>carry the weight",
     "each one big enough to rank", "#CC79A7"),
    (f"They concentrate in<br><b>one group</b>", f"{target_n:,} shoppers who want it, "
     f"now, and are stuck", OK),
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
section(1, "Four things have to go right",
        "A saved item does not fail in one way. The person has to come back to the "
        "list, find the item again, resolve whatever doubt they have about it, and "
        "get through checkout. Each step can fail on its own — so the first job is "
        "to say which step we are talking about.",
        S.STAGE_COLOUR["A"])

# The model drawn as a chain rather than stated as a paragraph. Four cards with
# arrows: the arrows are the content, because these are steps in sequence and
# four parallel columns would say they are four independent buckets.
steps = []
for s in S.STAGE_ORDER:
    spec = S.stages()[s]
    quiet = bool(spec.get("note")) and s in ("A", "B")
    chip = (f"<div style='display:inline-block;font-size:.65rem;padding:.1rem .4rem;"
            f"border:1px solid {HAIR};border-radius:3px;color:{MUTED};"
            f"margin-top:.35rem'>quiet by construction</div>" if quiet else "")
    steps.append(
        f"<div style='flex:1;min-width:160px;border-top:5px solid {S.STAGE_COLOUR[s]};"
        f"padding:.6rem .5rem .2rem 0'>"
        f"<div style='font-weight:750;font-size:1.02rem'>{spec['title']}</div>"
        f"<div style='font-size:.82rem;color:{MUTED};line-height:1.4;margin-top:.25rem'>"
        f"{spec['user_situation']}</div>{chip}</div>")
st.html("<div style='display:flex;flex-wrap:wrap;gap:.3rem;margin:.4rem 0 .3rem'>"
        + arrow.join(steps) + "</div>")

note("Two of the four are marked quiet on purpose. Forgetting a wishlist produces "
     "no complaint, and nobody posts about a list being hard to scroll — they just "
     "search for the item again. That silence is the biggest threat to this whole "
     "analysis, which is what the loudness test two steps below is for.")


# ============================================================== STEP 2
section(2, "Almost all of the conversation is about one step",
        "Every relevant record was scored against a list of 33 barriers that was "
        "frozen before any of it was read. Sorting those barriers back onto the four "
        "steps gives the picture below — drawn to scale.",
        S.STAGE_COLOUR["C"])

rows = [{"n": stage_n.get(s, 0), "title": S.stage_title(s), "colour": S.STAGE_COLOUR[s]}
        for s in S.STAGE_ORDER]
st.plotly_chart(charts.journey(rows, height=150), width="stretch")

cols = st.columns(4)
for col, s in zip(cols, S.STAGE_ORDER):
    share = stage_n.get(s, 0) / band_total
    col.html(
        f"<div style='border-top:4px solid {S.STAGE_COLOUR[s]};padding-top:.5rem'>"
        f"<div style='font-size:1.75rem;font-weight:750;line-height:1'>{share:.0%}</div>"
        f"<div style='font-size:.86rem;margin-top:.15rem'>{S.stage_title(s)}</div>"
        f"<div style='font-size:.74rem;color:{MUTED}'>{stage_n.get(s, 0):,} records</div>"
        f"</div>")

verdict(f"<b>{S.stage_title(lead)}</b> carries {lead_share:.0%} of the conversation — "
        f"more than the other three steps combined, several times over.",
        S.STAGE_COLOUR["C"])
note("Width is share of conversation, <b>not</b> drop-off. A record can raise barriers "
     "at more than one step, so these describe emphasis rather than a population being "
     "whittled down. There is no funnel here and the shape deliberately does not draw one.")


# ============================================================== STEP 3
section(3, "But a loud step is not necessarily a big one",
        "This is the objection that could sink the whole project: two of the four "
        "steps are silent by construction, so picking the busiest one on volume alone "
        "would be the easiest possible way to get this wrong.",
        BAD)

if inv.empty:
    st.info("Inversion threshold not computed.")
else:
    leader_row = inv[inv["inversion_factor"].isna()]
    leader_n = int(leader_row["n"].iloc[0]) if not leader_row.empty else int(inv["n"].max())
    leader_name = (S.stage_title(str(leader_row["stage"].iloc[0]))
                   if not leader_row.empty else S.stage_title(lead))

    # The arithmetic, spelled out once in words before it is drawn. A reader who
    # understands this sentence understands the chart without a legend.
    st.html(
        f"<div style='display:flex;flex-wrap:wrap;gap:.5rem;align-items:stretch;"
        f"margin:.5rem 0 1rem'>"
        f"<div style='flex:1;min-width:190px;border:1px solid {HAIR};border-radius:6px;"
        f"padding:.7rem .85rem'><div style='font-size:.72rem;color:{MUTED};"
        f"letter-spacing:.08em'>WE OBSERVED</div>"
        f"<div style='font-size:1.5rem;font-weight:750'>{leader_n:,}</div>"
        f"<div style='font-size:.82rem'>records blaming <b>{leader_name}</b></div></div>"
        f"<div style='align-self:center;color:{MUTED};font-size:1.3rem'>&rsaquo;</div>"
        f"<div style='flex:2;min-width:260px;border:1px solid {HAIR};border-radius:6px;"
        f"padding:.7rem .85rem'><div style='font-size:.72rem;color:{MUTED};"
        f"letter-spacing:.08em'>SO WE ASK</div>"
        f"<div style='font-size:.95rem;line-height:1.45;margin-top:.15rem'>How badly "
        f"would we have to be <b>under-counting a quiet step</b> for it to overtake "
        f"{leader_n:,} and change the answer?</div></div></div>")

    d = inv[inv["inversion_factor"].notna()].copy()
    d["label"] = d["stage"].map(S.stage_title)
    d = d.sort_values("inversion_factor")
    d["colour"] = [BAD if f <= 3.0 else OK for f in d["inversion_factor"]]
    d["text"] = [f"  {f:.1f}× — we saw {int(n):,}, it would need {leader_n:,}"
                 for f, n in zip(d["inversion_factor"], d["n"])]

    fig = go.Figure(go.Bar(
        x=d["inversion_factor"], y=d["label"], orientation="h",
        marker_color=d["colour"], text=d["text"], textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:.1f}× under-reporting required<extra></extra>"))
    # The plausible-silence region, shaded rather than described. Everything
    # inside it is a stage whose ranking silence could genuinely explain.
    fig.add_vrect(x0=0, x1=3.0, fillcolor=BAD, opacity=0.09, line_width=0)
    # S3-MET-3: the fragility line is DRAWN, not captioned. A threshold that
    # lives only in prose is the number a reader skips.
    fig.add_vline(x=3.0, line_dash="dash", line_color=BAD, line_width=2,
                  annotation_text="3× — as much silence as is plausible",
                  annotation_position="top", annotation_font_size=11)
    fig.update_layout(
        height=90 + 62 * len(d), margin=dict(l=10, r=10, t=34, b=28),
        plot_bgcolor="rgba(0,0,0,0)", showlegend=False, bargap=0.45,
        xaxis=dict(range=[0, float(d["inversion_factor"].max()) * 1.62],
                   title="× more records than we saw, before the answer changes",
                   title_font_size=11, showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch")

    if tightest is not None:
        fragile = bool(int(tightest["fragile"]))
        verdict(
            (f"The closest call is <b>{S.stage_title(str(tightest['stage']))}</b> at "
             f"<b>{float(tightest['inversion_factor']):.1f}×</b> — ")
            + ("close enough that silence could plausibly explain it. Treat the choice "
               "of step as fragile and let the interviews settle it."
               if fragile else
               f"far past what silence can explain. <b>{leader_name} is where the "
               f"engine goes to work</b>, and that holds even if this corpus is deaf "
               f"to the quiet steps."),
            BAD if fragile else OK)


# ============================================================== STEP 4
section(4, f"Inside {S.stage_title(lead)}: what is actually stopping people",
        "Each bar is a barrier in the words shoppers used, not in ours. Grey bars sit "
        "under 30 records — shown, because a barrier nobody mentions is a result, but "
        "never ranked against the others.",
        "#CC79A7")

shown = prev[(prev["stage"] == lead) & (prev["n"] > 0) & (prev["code"] != "Z-99")].copy()
if shown.empty:
    st.info("No evidence recorded at this step.")
else:
    shown["label"] = shown["code"].map(S.chart_label)
    top = shown.sort_values("n", ascending=False)
    plot = top.head(12).sort_values("n")
    fig = go.Figure(go.Bar(
        x=plot["n"], y=plot["label"], orientation="h",
        marker_color=["#BBBBBB" if v < charts.MIN_N_RANKED else charts.PALETTE[0]
                      for v in plot["n"]],
        text=[f" {int(v):,}" for v in plot["n"]], textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,} records<extra></extra>"))
    fig.update_layout(
        height=120 + 34 * len(plot), margin=dict(l=10, r=10, t=10, b=30),
        plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
        xaxis=dict(range=[0, float(plot["n"].max()) * 1.16], showgrid=False,
                   zeroline=False, title="records mentioning it", title_font_size=11),
        yaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch")

    # Six cards instead of fourteen expanders. An expander that has to be
    # opened one at a time is a wall of clicks, and the mechanism line is the
    # part that actually tells a reader what could be built.
    st.html(f"<div style='font-weight:700;margin:.8rem 0 .1rem'>The six biggest, and "
            f"what each one really is</div>")
    grid = top.head(6).reset_index(drop=True)
    for start in (0, 3):
        for col, (_, r) in zip(st.columns(3), grid.iloc[start:start + 3].iterrows()):
            c = r["code"]
            rr = rel_by_code.get(c)
            if rr is not None and str(rr["verdict"]) in RELIABILITY:
                rcol, rtext = RELIABILITY[str(rr["verdict"])]
                kap = (f" · κ {float(rr['kappa']):.2f}" if int(rr["measurable"]) else "")
                chip = (f"<div style='font-size:.68rem;color:{rcol};margin-top:.5rem'>"
                        f"● {rtext}{kap}</div>")
            else:
                chip = ""
            col.html(
                f"<div style='border:1px solid {HAIR};border-radius:7px;padding:.75rem .8rem;"
                f"height:100%;min-height:172px'>"
                f"<div style='font-size:1.35rem;font-weight:750;line-height:1'>"
                f"{int(r['n']):,}</div>"
                f"<div style='font-size:.72rem;color:{MUTED};margin-bottom:.45rem'>"
                f"records · {int(r['n_distinct_authors']):,} different people · "
                f"{float(r['share']):.0%} of all talk</div>"
                f"<div style='font-weight:650;font-size:.93rem;line-height:1.35'>"
                f"“{S.voice(c)}”</div>"
                f"<div style='font-size:.81rem;color:{MUTED};line-height:1.4;"
                f"margin-top:.3rem'>{S.plain(c)}</div>{chip}</div>")

    # What is INSIDE the biggest barrier. Its headline number says how often it
    # comes up; only the split says what could be built for it.
    big = str(top.iloc[0]["code"])
    sub = db.query("SELECT * FROM analysis_subcode WHERE theme = ? ORDER BY n DESC", (big,))
    if not sub.empty:
        st.html(f"<div style='font-weight:700;margin:1.4rem 0 .1rem'>Inside the biggest "
                f"one — “{S.voice(big)}”</div>")
        note("A barrier's headline number does not tell you what to build; this split "
             "does. A record can carry more than one, so these add to more than 100%.")
        d2 = sub.copy().sort_values("n")
        d2["what"] = d2["subcode"].map(
            lambda x: "not specific enough to place" if x == "unclear"
            else F.subcode_label(big, x))
        fig = go.Figure(go.Bar(
            x=d2["share"], y=d2["what"], orientation="h",
            marker_color=[charts.PALETTE[2] if s != "unclear" else "#BBBBBB"
                          for s in d2["subcode"]],
            text=[f" {v:.0%}  ({int(n):,})" for v, n in zip(d2["share"], d2["n"])],
            textposition="outside", cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:.0%} of this barrier<extra></extra>"))
        fig.update_layout(
            height=100 + 34 * len(d2), margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
            xaxis=dict(range=[0, float(d2["share"].max()) * 1.3], visible=False),
            yaxis=dict(showgrid=False))
        st.plotly_chart(fig, width="stretch")

    # Co-occurrence, cut from ten pairs to three. Lift is the one statistic here
    # a newcomer will not know, so it is drawn as a comparison to chance rather
    # than printed as a number with a footnote.
    # Restricted to pairs where BOTH barriers belong to the step this section is
    # about. Unfiltered, the strongest pairing in the whole corpus is two
    # Coming-back barriers — a real finding, but printed under "inside Deciding
    # on the item" it simply reads as a mistake.
    co = db.query("""SELECT * FROM analysis_cooccurrence
                     WHERE min_support_met = 1 AND code_a <> 'Z-99' AND code_b <> 'Z-99'
                     ORDER BY lift DESC""")
    if not co.empty:
        co = co[(co["code_a"].map(S.stage_of) == lead)
                & (co["code_b"].map(S.stage_of) == lead)].head(3)
    if not co.empty:
        st.html(f"<div style='font-weight:700;margin:1.4rem 0 .1rem'>Barriers that "
                f"travel together</div>")
        note("Two barriers raised by the same person far more often than chance would "
             "produce are likely <b>one compound problem with one fix</b>. Ranked by how "
             "surprising the pairing is, not by how often it happens — two very common "
             "barriers co-occur a lot by accident.")
        for col, (_, r) in zip(st.columns(len(co)), co.iterrows()):
            lift = float(r["lift"])
            col.html(
                f"<div style='border:1px solid {HAIR};border-radius:7px;padding:.75rem .8rem;"
                f"height:100%;min-height:180px'>"
                f"<div style='font-size:.9rem;font-weight:650;line-height:1.35'>"
                f"“{S.voice(r['code_a'])}”</div>"
                f"<div style='color:{MUTED};font-size:.78rem;margin:.3rem 0'>+</div>"
                f"<div style='font-size:.9rem;font-weight:650;line-height:1.35'>"
                f"“{S.voice(r['code_b'])}”</div>"
                f"<div style='margin-top:.6rem;height:6px;background:{HAIR};"
                f"border-radius:3px;overflow:hidden'>"
                f"<div style='width:{min(lift / 14 * 100, 100):.0f}%;height:100%;"
                f"background:{charts.PALETTE[3]}'></div></div>"
                f"<div style='font-size:.78rem;margin-top:.35rem'>"
                f"<b>{lift:.1f}× more often than chance</b></div>"
                f"<div style='font-size:.72rem;color:{MUTED}'>"
                f"{int(r['n_joint'])} people raised both</div></div>")

# The pre-registration, and every barrier that found nothing. Collapsed because
# it is a defence rather than a finding — but kept in the page, because a
# barrier list assembled after the fact would be worthless and the only proof
# that this one was not is the list itself.
with st.expander("All 33 barriers — the list was frozen before a single record was read"):
    note("Committed to the repository with a version string and a date <b>before "
         "collection</b>. That is the defence against finding what you expected to "
         "find: the engine cannot invent a category mid-analysis to fit a result it "
         "likes. Barriers that turned out to have no evidence are still shown, greyed — "
         "a barrier nobody mentions is a result; a barrier never <i>checked</i> would "
         "be a hole.")

    def _barrier(code: str, n: int) -> str:
        grey = "" if n else f";color:{MUTED}"
        foot = f"{n} records" if n else "no evidence found"
        return (f"<div style='font-size:.82rem;line-height:1.3;margin-bottom:.45rem"
                f"{grey}'>“{S.voice(code)}”<br><span style='color:{MUTED};"
                f"font-size:.72rem'>{foot} · {S.tag(code)}</span></div>")

    # Stage C gets a double-width column split in two: it holds 14 of the 33, and
    # four equal columns leave three stubs beside one long one — a shape that says
    # "one big category" rather than "this is where everything happens".
    for col, stg in zip(st.columns([1, 1, 2, 1]), S.STAGE_ORDER):
        with col:
            st.html(f"<div style='border-top:4px solid {S.STAGE_COLOUR[stg]};"
                    f"padding-top:.45rem;font-weight:700'>{S.stage_title(stg)}</div>"
                    f"<div style='color:{MUTED};font-size:.74rem;margin-bottom:.5rem'>"
                    f"{stage_n.get(stg, 0):,} records</div>")
            rs = prev[prev["stage"] == stg].sort_values("n", ascending=False)
            items = [_barrier(r["code"], int(r["n"])) for _, r in rs.iterrows()]
            if len(items) > 8:
                half = (len(items) + 1) // 2
                for sub_col, chunk in zip(st.columns(2), (items[:half], items[half:])):
                    sub_col.html("".join(chunk))
            else:
                st.html("".join(items))


# ============================================================== STEP 5
section(5, "Who is stuck there",
        "The groups below are not a second opinion laid over the data. They fall out "
        "of the step we just chose: whether someone has an unresolved doubt is exactly "
        "what “decided” means, so three questions the classification has already "
        "answered split every person into one of six groups.",
        OK)

if seg.empty:
    st.info("Segments not derived yet.")
else:
    n_root = sum(seg_by_id.values())
    no_intent = seg_by_id.get(1, 0) + seg_by_id.get(2, 0)
    live = seg_by_id.get(3, 0) + seg_by_id.get(4, 0) + seg_by_id.get(5, 0) + seg_by_id.get(6, 0)
    soon = seg_by_id.get(3, 0) + seg_by_id.get(4, 0)
    later = seg_by_id.get(5, 0) + seg_by_id.get(6, 0)

    # The derivation drawn as the decision tree it actually is. This was three
    # numbered sentences of prose, which asks a reader to hold a branching
    # structure in their head — the one thing a diagram does for free.
    #
    # Drawn in Plotly rather than as inline SVG on purpose: `st.html` runs its
    # input through a sanitiser that DROPS <svg> entirely, leaving the wrapper
    # div and an empty gap where the diagram should be. It fails silently, so
    # it is only visible by looking at the rendered page. Plotly also inherits
    # the viewer's light/dark theme, which a hand-rolled SVG would not.
    # Plotly rejects 8-digit hex and bare-dot alpha, and `font.weight` is not
    # available on every version it may be installed against — so tints are
    # written as rgba() and emphasis as <b> markup, both of which are stable.
    C = S.STAGE_COLOUR["C"]
    RULE, TINT = "rgba(128,128,128,0.35)", "rgba(230,159,0,0.14)"
    tree = go.Figure()
    shapes, notes = [], []

    def node(x0, y0, w, label, count, *, sub="", accent=None, h=42):
        x1 = x0 + w
        shapes.append(dict(type="rect", x0=x0, y0=y0, x1=x1, y1=y0 + h,
                           line=dict(color=accent or RULE, width=1.6),
                           fillcolor=TINT if accent else "rgba(0,0,0,0)",
                           layer="below"))
        head = f"<b>{label}</b>" if accent else label
        notes.append(dict(x=x0 + 12, y=y0 + (15 if sub else h / 2), text=head,
                          xanchor="left", yanchor="middle", showarrow=False,
                          font=dict(size=12.5, color=accent) if accent
                          else dict(size=12.5)))
        notes.append(dict(x=x1 - 12, y=y0 + (15 if sub else h / 2),
                          text=f"<b>{count:,}</b>", xanchor="right",
                          yanchor="middle", showarrow=False,
                          font=dict(size=13, color=accent) if accent
                          else dict(size=13)))
        if sub:
            notes.append(dict(x=x0 + 12, y=y0 + 31, text=sub, xanchor="left",
                              yanchor="middle", showarrow=False,
                              font=dict(size=10.5, color=MUTED)))

    def elbow(x1, y1, x2, y2):
        mid = x1 + (x2 - x1) / 2
        shapes.append(dict(type="path", path=f"M {x1},{y1} L {mid},{y1} "
                                             f"L {mid},{y2} L {x2},{y2}",
                           line=dict(color=RULE, width=1.6), layer="below"))

    for x, txt, col in ((196, "① ANY LIVE INTENT?", MUTED),
                        (406, "② SOON, OR LATER?", MUTED),
                        (596, "③ IS THE DOUBT RESOLVED?", C)):
        notes.append(dict(x=x, y=18, text=f"<b>{txt}</b>", xanchor="left",
                          yanchor="middle", showarrow=False,
                          font=dict(size=10.5, color=col)))

    elbow(150, 181, 196, 95);  elbow(150, 181, 196, 267)
    elbow(346, 95, 406, 69);   elbow(346, 95, 406, 121)
    elbow(346, 267, 406, 212); elbow(346, 267, 406, 322)
    elbow(536, 212, 596, 193); elbow(536, 212, 596, 245)
    elbow(536, 322, 596, 309); elbow(536, 322, 596, 361)

    # Two lines: "Everyone we heard from" on one line runs straight through
    # the right-aligned count at this box width.
    node(0, 160, 150, "Everyone", n_root, sub="relevant records")
    node(196, 74, 150, "No live intent", no_intent)
    node(196, 246, 150, "Wants to buy", live)
    node(406, 48, 130, "Collectors", seg_by_id.get(1, 0))
    node(406, 100, 130, "Lapsed", seg_by_id.get(2, 0))
    node(406, 191, 130, "Soon", soon)
    node(406, 301, 130, "Later", later)
    node(596, 172, 244, "Ready Buyers", seg_by_id.get(3, 0),
         sub="decided — nothing in the way")
    node(596, 224, 244, "Stuck Deciders", seg_by_id.get(4, 0),
         sub="a doubt is still blocking them", accent=C)
    node(596, 288, 244, "Committed Waiters", seg_by_id.get(5, 0),
         sub="decided, waiting on a condition")
    node(596, 340, 244, "Hesitant Waiters", seg_by_id.get(6, 0),
         sub="waiting, and still unsure")

    tree.update_layout(
        shapes=shapes, annotations=notes, height=420,
        margin=dict(l=4, r=4, t=4, b=4), dragmode=False,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(range=[-4, 846], visible=False, fixedrange=True),
        yaxis=dict(range=[392, 4], visible=False, fixedrange=True))
    st.plotly_chart(tree, width="stretch", config={"displayModeBar": False})

    note(f"Question ③ is the link back to step 4: <b>any unresolved barrier from "
         f"{S.stage_title(lead)} means the person has not decided.</b> A voiced doubt "
         f"is an undecided decision — which is why these groups are a re-cut of the "
         f"same evidence rather than a new opinion, and why they cover 100% of the "
         f"corpus where an earlier motivation-based segmentation reached 6.6%.")

    verdict(f"<b>Stuck Deciders</b> are the largest group at {target_n:,} "
            f"({target_n / n_root:.0%}) — they want the item, they want it soon, and "
            f"something specific is in the way. Which group is actually worth building "
            f"for is argued on <b>Insights</b>, where size is only one of four tests.",
            OK)


# ============================================================== the checks
st.html(f"<div style='margin:2.6rem 0 .4rem'><div style='height:1px;background:{HAIR}'>"
        f"</div><div style='font-size:1.15rem;font-weight:700;margin-top:1rem'>"
        f"If you want to attack this</div>"
        f"<div style='color:{MUTED};font-size:.9rem;max-width:70ch;line-height:1.5'>"
        f"Everything a sceptic should check, kept off the argument above so it stays "
        f"readable — and kept in the app, so it is never only in a repository.</div></div>")

a, b, c, d = st.columns(4)
a.metric("Relevant records", f"{denom:,}")
# Z-99 is the residual bucket, not a barrier. Counting it made this read
# "32 of 34" against a page that says 33 everywhere else.
real = prev[prev["code"] != "Z-99"]
b.metric("Barriers with evidence", f"{int((real['n'] > 0).sum())} of {len(real)}")
z = prev[prev["code"] == "Z-99"]
if not z.empty:
    c.metric("Relevant but unmatched", f"{float(z['share'].iloc[0]):.1%}")
spans = db.query("SELECT sum(span_verified) AS ok, count(*) AS n FROM classifications")
if not spans.empty and spans["n"].iloc[0]:
    ok_n, n_all = int(spans["ok"].iloc[0]), int(spans["n"].iloc[0])
    d.metric("Quotes verified word-for-word", f"{ok_n / n_all:.1%}")

with st.expander("How far can the labels be trusted? — machine against a human coder"):
    note("A person hand-labelled a sample of records without ever seeing what the "
         "classifier decided. Where enough of those labels carry a barrier, the two can "
         "be compared. <b>κ</b> is agreement after chance is removed: 0 is coin-flip, "
         "1 is perfect, and roughly 0.6 is the usual bar for “reliable”. Only the "
         "measurable ones are shown — the rest have too few hand labels to say anything.")
    m = rel[rel["measurable"] == 1].sort_values("kappa", ascending=False) if not rel.empty \
        else pd.DataFrame()
    if m.empty:
        st.info("No barrier has enough hand labels to measure agreement.")
    else:
        for _, r in m.iterrows():
            k = float(r["kappa"])
            rcol, rtext = RELIABILITY.get(str(r["verdict"]), (MUTED, str(r["verdict"])))
            st.html(
                f"<div style='display:flex;align-items:center;gap:.7rem;margin:.35rem 0'>"
                f"<div style='flex:2;min-width:180px;font-size:.87rem'>"
                f"“{S.voice(str(r['code']))}”</div>"
                f"<div style='flex:3;height:9px;background:{HAIR};border-radius:5px;"
                f"position:relative;overflow:hidden'>"
                f"<div style='width:{max(k, 0) * 100:.0f}%;height:100%;background:{rcol}'>"
                f"</div></div>"
                f"<div style='width:172px;font-size:.78rem;color:{rcol};text-align:right'>"
                f"κ {k:.2f} · {rtext}</div></div>")
        st.html(f"<div style='color:{MUTED};font-size:.78rem;margin-top:.6rem'>"
                f"The weakest of these sits under the sharpest claim in the project, and "
                f"every page that leans on it says so. It is carried into the interviews "
                f"as a question, never quoted as a finding.</div>")

with st.expander("What this corpus cannot tell you"):
    st.markdown("""
- **Two steps are under-detected by construction.** Forgetting produces no complaint, so
  a low count for *Coming back* is not evidence that it is small. That is the whole
  reason step 3 above exists.
- **A human agreed with the pipeline on 19 of 30 randomly drawn records** (63%, 95% CI
  45–78%). Every disagreement fell on a record the filter **rejected**; all 9 it accepted
  were confirmed. What is in this corpus belongs here — the open question is what is missing.
- **The relevance rule is deliberately narrow**, excluding post-purchase satisfaction and
  order/refund complaints. Admitting those would raise the material-quality and
  returns-trust counts more than the others, so **the ranking is conditional on that rule.**
- **Only ~36% of the corpus is Myntra-specific.** Platform-mechanical barriers are ranked
  on their Myntra-specific count, not the pooled one.
- **Reddit was collected through a third-party service** after its API proved unavailable.
  Disclosed rather than hidden.
""")

with st.expander("Is a barrier just an artefact of where it was found?"):
    note("If a barrier appears far more on one platform than across the corpus, it may be "
         "telling you about that platform's users rather than about shoppers. Read the two "
         "share columns against each other.")
    src = db.query("""SELECT source, code, n, share FROM analysis_source_code
                      WHERE n >= 15 ORDER BY js_divergence DESC, n DESC LIMIT 12""")
    if not src.empty:
        base = dict(zip(prev["code"], prev["share"]))
        lines = ["| platform | barrier | records | share here | share corpus-wide |",
                 "|---|---|---|---|---|"]
        for _, r in src.iterrows():
            lines.append(f"| {r['source']} | “{S.voice(r['code'])}” | {int(r['n'])} | "
                         f"{float(r['share']):.0%} | {base.get(r['code'], 0):.0%} |")
        st.markdown("\n".join(lines))
        note("Price talk at 53% on the Play Store against 20% corpus-wide is the clearest "
             "case: app-store reviews are written by people with a grievance, and that "
             "shapes what they raise.")

with st.expander("Provenance — every pipeline pass, its model, and what it cost"):
    runs = db.query("SELECT stage, model, n_output, cost_usd, started_at FROM runs "
                    "WHERE n_output > 0 ORDER BY started_at DESC LIMIT 12")
    if not runs.empty:
        lines = ["| pass | model | outputs | cost (est.) | run at |", "|---|---|---|---|---|"]
        for _, r in runs.iterrows():
            lines.append(f"| {r['stage']} | {r['model']} | {int(r['n_output']):,} | "
                         f"${float(r['cost_usd'] or 0):.2f} | {str(r['started_at'])[:16]} |")
        st.markdown("\n".join(lines))
        note("Costs are token-count estimates, not billing.")

# B-5: the exit-gate reports must be readable IN THE APP, not only in the repo.
REPORTS = Path(__file__).resolve().parents[2] / "evals" / "reports"
gates = sorted(REPORTS.glob("gate_P*.md"), reverse=True)
if gates:
    # One expander per report, NOT an expander of expanders: Streamlit forbids
    # nesting them and raises rather than degrading.
    note("Each phase ended with a gate. These are the reports those gates produced, "
         "unedited — including the checks they found failing.")
    for g in gates:
        with st.expander(g.stem.replace("_", " ").replace("gate ", "Exit gate ")):
            st.markdown(g.read_text())
