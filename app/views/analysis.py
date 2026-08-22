"""Analysis — the user journey, and where it breaks.

STRUCTURED AROUND THE JOURNEY, NOT THE CODEBOOK
-----------------------------------------------
This page used to open with a ranked list of code ids: "C2 · 241 · 0.237". That
is legible to whoever wrote the codebook and to nobody else. A first-time reader
needs the model before any number means anything — a saved item must survive
four things, and the codes are the specific ways each one fails.

So the order here is: teach the four stages, show where the conversation
actually sits, then let a reader open a stage to see its failure modes in the
users' own words. Code ids appear, but always in small type beside a plain-
language label, never as the thing a reader has to decode first.

Design rule from architecture.md §4.2 is unchanged: this page performs NO
aggregation over raw records. Everything is a SELECT from a materialised
analysis_* table.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from lib import charts, db, framework as F, story as S

st.title("Where the journey breaks")
st.caption("Every relevant record scored against a barrier list that was fixed "
           "before any of it was read.")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

prev = db.query("SELECT * FROM analysis_code_prevalence ORDER BY n DESC")
if prev.empty:
    st.info("Classification has not run yet."); st.stop()

denom = int(prev["denominator"].iloc[0])
prev["stage"] = prev["code"].map(S.stage_of)

st.markdown(S.THE_MODEL)
st.warning(S.PROXY_WARNING, icon="⚠️")

# ------------------------------------------------------------ the journey
stage_n = db.query("SELECT stage, sum(n) AS n FROM analysis_stage_outcome GROUP BY stage")
stage_n = {r["stage"]: int(r["n"]) for _, r in stage_n.iterrows()}

st.subheader("Four things have to go right")
rows = [{"n": stage_n.get(s, 0), "title": S.stage_title(s), "colour": S.STAGE_COLOUR[s]}
        for s in S.STAGE_ORDER]
st.plotly_chart(charts.journey(rows), width="stretch")
st.caption("Width is share of coded conversation, not drop-off. A record can raise "
           "barriers at more than one stage, so the parts describe emphasis rather "
           "than a population being whittled down.")

cols = st.columns(4)
for col, s in zip(cols, S.STAGE_ORDER):
    spec = S.stages()[s]
    with col:
        st.markdown(f"<div style='border-top:4px solid {S.STAGE_COLOUR[s]};padding-top:.6rem'>"
                    f"<b>{spec['title']}</b></div>", unsafe_allow_html=True)
        st.caption(spec["user_situation"])
        st.metric("records", f"{stage_n.get(s,0):,}")
        st.caption(f"{stage_n.get(s,0)/denom:.0%} of all relevant records")
        if spec.get("note"):
            st.caption(f"⚠️ {' '.join(spec['note'].split())}")

# The decision of WHICH step to work on is made here, so the test that
# defends it belongs here too rather than on Insights, where it used to sit
# under weight sensitivity. Insights decides which BARRIER; this page decides
# which STEP, and each should carry its own defence.
lead = max(S.STAGE_ORDER, key=lambda x: stage_n.get(x, 0))
st.markdown(f"#### Step 3 carries most of it — but a loud step is not a big one")
st.caption(
    "Two of these four stages are quiet **by construction**, not because they are small. "
    "Forgetting a wishlist produces no complaint, and nobody posts about a list being "
    "hard to scroll — they just search for the item again. So picking the busiest stage "
    "on volume alone would be the single easiest way to get this project wrong.\n\n"
    "Rather than accept the ranking or discard it, the engine asks how *wrong* the counts "
    "would have to be for the answer to change: **the multiplier by which each quiet "
    "stage would have to be under-reported to overtake the leader.** Roughly 2–3× is "
    "plausible for a silent barrier; beyond that the choice is safe.")

inv = db.query("SELECT * FROM analysis_stage_inversion ORDER BY n DESC")
if inv.empty:
    st.info("Inversion threshold not computed.")
else:
    d = inv.copy()
    d["label"] = d["stage"].map(S.stage_title)
    d["factor"] = d["inversion_factor"].fillna(0.0)
    leader = d.loc[d["inversion_factor"].isna(), "stage"]
    fig = charts.bar(d[d["inversion_factor"].notna()].sort_values("factor"),
                     "label", "factor", orientation="h", height=280,
                     title="Under-reporting needed to overtake "
                           f"{S.stage_title(leader.iloc[0]) if len(leader) else '?'} (×)")
    # S3-MET-3: the fragility line is DRAWN, not described. A threshold that
    # lives only in a caption is the number a reader skips.
    fig.add_vline(x=3.0, line_dash="dash", line_color="#D55E00",
                  annotation_text="3× — plausible for a silent barrier",
                  annotation_position="top")
    st.plotly_chart(fig, width="stretch")

    ranked_inv = inv[inv["inversion_factor"].notna()].sort_values("inversion_factor")
    if not ranked_inv.empty:
        tightest = ranked_inv.iloc[0]
        (st.warning if int(tightest["fragile"]) else st.success)(
            f"The tightest is **{S.stage_title(str(tightest['stage']))}** at "
            f"**{float(tightest['inversion_factor']):.1f}×**"
            + (", which silence could plausibly explain — treat the stage choice as "
               "fragile and let the interviews settle it."
               if int(tightest["fragile"]) else
               ", comfortably past what silence can explain. **Deciding on the item is "
               "where the engine goes to work**, and that choice survives the objection "
               "that this corpus cannot hear the quiet stages."),
            icon="⚖️" if int(tightest["fragile"]) else "✅")

st.divider()

tab_stuck, tab_who, tab_pairs, tab_how = st.tabs(
    ["Where people get stuck", "Who gets stuck", "Barriers that travel together",
     "How we know this"])

# ------------------------------------------------------- where people stick
with tab_stuck:
    with st.expander("The full barrier list, by step — frozen before any record was read"):
        st.caption(
            "All 33 barriers were committed to the repository with a version string and a "
            "date **before a single record was read**. That is the defence against finding "
            "what you expected to find: the engine cannot invent a category mid-analysis "
            "to fit a result it likes. Barriers that turned out to have no evidence are "
            "still shown, greyed — a barrier nobody mentions is a result, and a barrier "
            "never *checked* would be a hole.")

        def _barrier_html(code: str, n: int) -> str:
            grey = "" if n else ";color:#6f6f6f"
            foot = f"{n} records · {S.tag(code)}" if n else f"no evidence · {S.tag(code)}"
            return (f"<div style='font-size:.83rem;line-height:1.3;margin-bottom:.42rem"
                    f"{grey}'>“{S.voice(code)}”<br><span style='color:#8a8a8a;"
                    f"font-size:.75rem'>{foot}</span></div>")

        # Stage C is given a double-width column split into two lists: it holds 14
        # of the 33, and four equal columns leave three stubs beside one long one,
        # a shape that says "one big category" rather than "everything happens here".
        for col, stg in zip(st.columns([1, 1, 2, 1]), S.STAGE_ORDER):
            with col:
                st.html(f"<div style='border-top:4px solid {S.STAGE_COLOUR[stg]};"
                        f"padding-top:.45rem;font-weight:700'>{S.stage_title(stg)}</div>")
                st.caption(f"{stage_n.get(stg, 0):,} records")
                rows_s = prev[prev["stage"] == stg].sort_values("n", ascending=False)
                items = [_barrier_html(r["code"], int(r["n"])) for _, r in rows_s.iterrows()]
                if len(items) > 8:
                    half = (len(items) + 1) // 2
                    for sub, chunk in zip(st.columns(2), (items[:half], items[half:])):
                        sub.html("".join(chunk))
                else:
                    st.html("".join(items))

    st.caption("Each bar is a barrier in the words people actually used. The code in "
               "brackets is the framework id, for cross-referencing — you do not need "
               "it to read the chart.")

    pick = st.radio("Show", ["Everything"] + [S.stage_title(s) for s in S.STAGE_ORDER],
                    horizontal=True, label_visibility="collapsed")
    sel = prev if pick == "Everything" else prev[
        prev["stage"] == next(s for s in S.STAGE_ORDER if S.stage_title(s) == pick)]

    shown = sel[(sel["n"] > 0) & (sel["code"] != "Z-99")].copy()
    if shown.empty:
        st.info("No evidence recorded at this stage.")
    else:
        shown["label"] = shown["code"].map(S.chart_label)
        st.plotly_chart(
            charts.bar(shown.sort_values("n").tail(14), "label", "n",
                       title="How often each barrier comes up", n_col="n",
                       orientation="h", height=max(300, 34 * min(len(shown), 14) + 90)),
            width="stretch")
        st.caption("Grey bars sit below 30 records — shown, never ranked. " + S.explain("n"))

        st.markdown("**What each one actually is**")
        for _, r in shown.sort_values("n", ascending=False).head(14).iterrows():
            c = r["code"]
            with st.expander(f"**{S.voice(c)}**  ·  {int(r['n'])} records"):
                st.markdown(f"{S.plain(c)}")
                a, b, d = st.columns(3)
                a.metric("records", f"{int(r['n']):,}")
                b.metric("different people", f"{int(r['n_distinct_authors']):,}")
                d.metric("share of conversation", f"{float(r['share']):.1%}")
                st.caption(f"Analytic name **{S.name(c)}** · framework code "
                           f"`{S.tag(c)}` · appears on {int(r['n_sources'])} of the "
                           f"4 sources · mean classifier confidence "
                           f"{float(r['mean_confidence'] or 0):.2f}")
                if int(r["below_min_n"]):
                    st.warning("Below 30 records — reportable, but not rankable "
                               "against the others.", icon="⚠️")

        sub = db.query("SELECT * FROM analysis_subcode WHERE theme = ? ORDER BY n DESC",
                       (str(shown.sort_values("n", ascending=False).iloc[0]["code"]),))
        if not sub.empty:
            top = str(shown.sort_values("n", ascending=False).iloc[0]["code"])
            st.markdown(f"**Inside the biggest one — “{S.voice(top)}”**")
            st.caption("A barrier's headline number does not tell you what to build. "
                       "The split below does. Records can carry more than one, so these "
                       "add to more than 100%.")
            d2 = sub.copy()
            d2["what it is"] = d2["subcode"].map(lambda x: F.subcode_label(top, x))
            d2["share of this barrier"] = d2["share"].map(lambda v: f"{v:.0%}")
            st.dataframe(d2[["what it is", "n", "share of this barrier"]],
                         width="stretch", hide_index=True)

    zero = prev[prev["n"] == 0]
    if not zero.empty and pick == "Everything":
        with st.expander(f"{len(zero)} barriers with no evidence at all — reported, not hidden"):
            st.caption("A barrier nobody mentions is a result. A barrier never *checked* "
                       "would be a hole, which is why the list was fixed in advance and "
                       "every entry is still shown.")
            for c in zero["code"]:
                st.markdown(f"- **{S.voice(c)}** · `{S.tag(c)}`")

# ------------------------------------------------------------- who gets stuck
with tab_who:
    seg = db.query("""SELECT segment_id, segment_name, count(*) AS n FROM segments_v2
                      GROUP BY segment_id, segment_name ORDER BY segment_id""")
    if seg.empty:
        st.info("Segments not derived yet.")
    else:
        st.markdown("#### These groups come out of the item-decision stage")
        st.markdown(S.SEGMENT_DERIVATION)
        st.divider()

        for _, r in seg.iterrows():
            sid = int(r["segment_id"])
            star = "  ⭐ **target**" if sid == F.TARGET_SEGMENT else ""
            with st.container(border=True):
                a, b = st.columns([3, 1])
                a.markdown(f"**{S.segment_label(sid)}**{star}")
                a.caption(S.segment_blurb(sid))
                b.metric("people", f"{int(r['n']):,}")
                b.caption(f"{int(r['n'])/denom:.0%} of everyone")

        st.divider()
        st.markdown(f"#### What stops **{S.segment_label(F.TARGET_SEGMENT)}** specifically")
        sc = db.query("""SELECT * FROM analysis_segment_code_v2
                         WHERE segment_id = ? AND n >= 15 ORDER BY n DESC""",
                      (F.TARGET_SEGMENT,))
        if sc.empty:
            st.info("No barrier in this group reaches the visibility floor.")
        else:
            base = dict(zip(prev["code"], prev["share"]))
            sc["lift"] = sc.apply(
                lambda r: r["share"] / base[r["code"]] if base.get(r["code"]) else None, axis=1)
            for _, r in sc.iterrows():
                c = r["code"]
                lift = float(r["lift"] or 0)
                flag = ("  —  **{:.1f}× more than everyone else**".format(lift)
                        if lift >= 1.5 else "")
                st.markdown(f"- **{S.voice(c)}** · {int(r['n'])} people, "
                            f"{float(r['share']):.0%} of the group{flag}")
            st.caption(S.explain("lift"))
            st.info("Lift here is **partly built in**: this group is *defined* as the "
                    "people with an unresolved item-level doubt, so item-level doubts "
                    "are bound to concentrate in it. It still ranks them against each "
                    "other usefully — it just cannot prove the group is special.",
                    icon="🔁")

# --------------------------------------------------------------- pairs
with tab_pairs:
    co = db.query("""SELECT * FROM analysis_cooccurrence
                     WHERE min_support_met = 1 AND code_a <> 'Z-99' AND code_b <> 'Z-99'
                     ORDER BY lift DESC LIMIT 10""")
    if co.empty:
        st.info("No pairs above the minimum-support floor.")
    else:
        st.markdown(S.explain("cooccurrence"))
        st.caption("Ranked by how *surprising* the pairing is, not by how often it "
                   "happens. Two very common barriers will co-occur a lot by chance; "
                   "that is not evidence they are connected.")
        for _, r in co.iterrows():
            with st.container(border=True):
                st.markdown(f"**{S.voice(r['code_a'])}**")
                st.markdown(f"…together with **{S.voice(r['code_b'])}**")
                st.caption(f"{int(r['n_joint'])} records raise both — "
                           f"**{float(r['lift']):.1f}× more often than chance**. "
                           f"`{S.tag(r['code_a'])}` × `{S.tag(r['code_b'])}`")

# ------------------------------------------------------------ how we know
with tab_how:
    st.caption("Everything a sceptic should check. Kept out of the pages above so "
               "they stay readable, kept in the app so it is never only in a repo.")

    st.markdown("#### What this corpus is")
    a, b, c, d = st.columns(4)
    a.metric("Relevant records", f"{denom:,}")
    b.metric("Barriers with evidence", f"{int((prev['n'] > 0).sum())} of {len(prev)}")
    z = prev[prev["code"] == "Z-99"]
    if not z.empty:
        c.metric("Unmatched", f"{float(z['share'].iloc[0]):.1%}")
    d.metric("Sources", "4")
    if not z.empty:
        st.caption(S.explain("residual"))

    st.markdown("#### Known limitations, stated rather than discovered")
    st.markdown("""
- **Two stages are under-detected by construction.** Forgetting produces no complaint, so
  a low count for *Coming back* is not evidence that it is small.
- **A human agreed with the pipeline on 19 of 30 randomly drawn records** (63%, Wilson 95%
  CI 45–78%). Every one of the 11 disagreements fell on a record the filter **rejected** —
  all 9 it accepted were confirmed. What is in this corpus belongs here; the open question
  is what is missing.
- **The relevance rule is deliberately narrow**, excluding post-purchase satisfaction and
  order/refund complaints. Admitting those would raise the material-quality and
  returns-trust counts more than the others, so **the ranking is conditional on that rule.**
- **Agreement with a human coder clears its threshold for only 2 of the 5 barriers with
  enough hand-labelled data to measure it.** *"I need to check with my partner"* is the
  least reliable of all and every claim resting on it says so.
- **Only ~36% of the corpus is Myntra-specific.** Platform-mechanical barriers are ranked
  on their Myntra-specific count, not the pooled one.
- **Reddit was collected through a third-party service** after its API proved unavailable.
  Disclosed rather than hidden.
""")

    st.markdown("#### Evidence quality")
    spans = db.query("SELECT sum(span_verified) AS ok, count(*) AS n FROM classifications")
    if not spans.empty and spans["n"].iloc[0]:
        ok, n = int(spans["ok"].iloc[0]), int(spans["n"].iloc[0])
        st.metric("Quotes verified word-for-word against the original record", f"{ok/n:.1%}")
        st.caption("Every quote shown anywhere in this app is checked as an exact substring "
                   "of the record it came from. A quote that is not exact is not evidence "
                   "and is never displayed.")

    with st.expander("Pipeline provenance — every pass, its model, and what it cost"):
        st.dataframe(
            db.query("SELECT stage, model, n_output, cost_usd, codebook_version, started_at"
                     " FROM runs WHERE n_output > 0 ORDER BY started_at DESC LIMIT 15"),
            width="stretch", hide_index=True)

    with st.expander("Is a barrier just an artefact of where it was found?"):
        st.caption("If a barrier appears far more on one platform than across the corpus, "
                   "it may be telling you about that platform's users rather than about "
                   "shoppers. Divergence is highest where that risk is greatest.")
        src = db.query("""SELECT source, code, n, share, js_divergence
                          FROM analysis_source_code WHERE n >= 15
                          ORDER BY js_divergence DESC, n DESC LIMIT 20""")
        if not src.empty:
            src["barrier"] = src["code"].map(S.voice)
            src["share on this platform"] = src["share"].map(lambda v: f"{v:.0%}")
            src["share across the corpus"] = src["code"].map(
                dict(zip(prev["code"], prev["share"]))).map(lambda v: f"{v:.0%}")
            st.dataframe(
                src[["source", "barrier", "n", "share on this platform",
                     "share across the corpus"]].rename(columns={
                        "source": "platform", "n": "records"}),
                width="stretch", hide_index=True)
            st.caption("Read the two share columns against each other. Price talk sitting "
                       "at 53% on the Play Store against 20% corpus-wide is the clearest "
                       "case: app-store reviews are written by people with a grievance, "
                       "and that shapes what they raise.")

    # B-5: the gate reports must be readable IN THE APP, not only in the repo.
    REPORTS = Path(__file__).resolve().parents[2] / "evals" / "reports"
    gates = sorted(REPORTS.glob("gate_P*.md"), reverse=True)
    if gates:
        st.markdown("#### Exit gate reports")
        st.caption("What each phase's gate actually found, including what it found failing.")
        for g in gates:
            with st.expander(g.stem.replace("_", " ").replace("gate ", "Gate ")):
                st.markdown(g.read_text())
