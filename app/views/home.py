"""Home — the method, in the order the decisions were actually made.

WHY THIS PAGE IS THE PROCESS AND NOT THE ANSWER
-----------------------------------------------
The previous version led with the question and then handed over the top three
barriers. That is the finding, and the finding is what Analysis and Insights
are for. A reader arriving here cannot judge whether the top three are worth
anything until they know how the field was narrowed: what was read, what was
thrown away and on what rule, how one of four steps was chosen over the other
three, how one group of shoppers was chosen inside that step, and what the
ranking is made of.

So this page is the chain of narrowing decisions, each shown with the number
that forced it and the check that could have overturned it:

    four steps  ->  which barriers live at each  ->  what was read
    ->  which step the conversation is actually about  ->  who inside it
    ->  what to solve first  ->  what would prove it wrong

Every figure is still a SELECT from a materialised analysis_* table. This page
computes one thing the pipeline does not store: the equal-weight decomposition
of the opportunity score, which is arithmetic on six stored columns and not an
aggregation over records.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from lib import charts, db, framework as F, story as S

ROOT = Path(__file__).resolve().parents[1]

st.title("How this engine gets to an answer")
st.caption("The question is *why don't people buy what they saved?* — this page is the "
           "method that answers it: what was read, how the field was narrowed at each "
           "step, and what could still overturn it. The findings themselves live on "
           "**Analysis** and **Insights**.")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

prev = db.query("SELECT * FROM analysis_code_prevalence ORDER BY n DESC")
if prev.empty:
    st.info("The classification pass has not run yet.")
    st.stop()

denom = int(prev["denominator"].iloc[0])
prev["stage"] = prev["code"].map(S.stage_of)
stage_n = {r["stage"]: int(r["n"]) for _, r in
           db.query("SELECT stage, sum(n) AS n FROM analysis_stage_outcome "
                    "GROUP BY stage").iterrows()}

st.warning(S.PROXY_WARNING, icon="⚠️")

# ============================================================ 1. the model
st.header("1 · A saved item has to survive four things")
st.markdown(S.THE_MODEL)

# One flex row rather than four st.columns: the arrows are the point. Four
# cards side by side read as four buckets, which is the exact misreading the
# vocabulary layer exists to prevent — these are sequential, and a barrier at
# step 3 is only reachable by someone who got through steps 1 and 2.
cards = []
for i, s in enumerate(S.STAGE_ORDER, 1):
    spec = S.stages()[s]
    n_codes = int((prev["stage"] == s).sum())
    cards.append(
        f"<div style='flex:1;min-width:150px;display:flex;flex-direction:column;"
        f"border-top:5px solid {S.STAGE_COLOUR[s]};padding:.6rem .5rem 0 0'>"
        f"<div style='font-size:.68rem;letter-spacing:.1em;color:#8a8a8a'>STEP {i}</div>"
        f"<div style='font-weight:700;font-size:1.05rem;margin:.15rem 0'>{spec['title']}</div>"
        f"<div style='font-size:.85rem;color:#9a9a9a;line-height:1.35'>{spec['question']}</div>"
        f"<div style='font-size:.78rem;color:{S.STAGE_COLOUR[s]};margin-top:auto;"
        f"padding-top:.5rem'>{n_codes} ways it can fail</div></div>")
arrow = ("<div style='align-self:center;color:#6a6a6a;font-size:1.4rem;"
         "padding:0 .35rem'>&rsaquo;</div>")
st.html("<div style='display:flex;flex-wrap:wrap;gap:.2rem;margin:.8rem 0 .4rem'>"
        + arrow.join(cards) + "</div>")
st.caption("These are four things that must go *right in sequence*, not four buckets. "
           "The engine's whole job is to find out which of the four the conversation is "
           "actually about, and then which specific failure inside it.")

# ================================================ 2. the barriers per step
st.header("2 · Every way each step can fail, written down in advance")
st.caption(
    "This list was **frozen before a single record was read** — 33 barriers, committed to "
    "the repository with a version string and a date. That is the whole defence against "
    "finding what you expected to find: the engine cannot invent a category mid-analysis "
    "to fit a result it likes. Barriers that turned out to have no evidence are still "
    "shown below, greyed, because a barrier nobody mentions is a result and a barrier "
    "never *checked* would be a hole.")

def _barrier(code: str, n: int) -> str:
    grey = "" if n else ";color:#6f6f6f"
    foot = f"{n} records · {S.tag(code)}" if n else f"no evidence · {S.tag(code)}"
    return (f"<div style='font-size:.83rem;line-height:1.3;margin-bottom:.42rem{grey}'>"
            f"“{S.voice(code)}”<br>"
            f"<span style='color:#8a8a8a;font-size:.75rem'>{foot}</span></div>")


# Step 3 gets a double-width column split into two lists. It carries 14 of the
# 33 barriers, so four equal columns leave three of them stubs beside one very
# long one — and the shape of that layout says "one big category", which is the
# opposite of the point. Two balanced sub-lists under a wider heading say
# "everything happens here" instead, which is what the numbers actually show.
for col, s in zip(st.columns([1, 1, 2, 1]), S.STAGE_ORDER):
    spec = S.stages()[s]
    with col:
        st.html(
            f"<div style='border-top:4px solid {S.STAGE_COLOUR[s]};padding-top:.45rem;"
            f"font-weight:700'>{spec['title']}</div>")
        st.caption(f"{stage_n.get(s, 0):,} records mention this step")
        rows = prev[prev["stage"] == s].sort_values("n", ascending=False)
        items = [_barrier(r["code"], int(r["n"])) for _, r in rows.iterrows()]
        if len(items) > 8:
            half = (len(items) + 1) // 2
            for sub, chunk in zip(st.columns(2), (items[:half], items[half:])):
                sub.html("".join(chunk))
        else:
            st.html("".join(items))

st.caption("A record can raise barriers at more than one step, so these counts describe "
           "emphasis, not a population being whittled down. **Deciding on the item carries "
           "14 of the 33 barriers and most of the conversation** — which is the first hint "
           "of where sections 4 and 5 are going.")

# ==================================================== 3. what was read
st.header("3 · What the engine read, and what it threw away")
st.caption(
    "Public conversation is the only data this project has — there is no access to "
    "Myntra's analytics. So the first question is not *what does it say* but *how much of "
    "it is about saving and buying at all.* Four sources were collected and cut down on "
    "stated rules, and every rejected record is logged with its reason and stays browsable "
    "on the **Data Bank** page.")

funnel = db.query("""
    SELECT (SELECT count(*) FROM records)                                AS collected,
           (SELECT count(*) FROM relevance)                              AS scored,
           (SELECT count(*) FROM relevance WHERE is_relevant = 1)        AS relevant,
           (SELECT count(DISTINCT r.author_hash) FROM records r
             WHERE r.author_hash IS NOT NULL
               AND r.record_id IN (SELECT record_id FROM classifications)
               AND r.record_id NOT IN (SELECT record_id FROM exclusions)) AS authors
""").iloc[0]

steps = [("Collected from four public sources", int(funnel.collected),
          "YouTube comments, Reddit threads, Play Store and App Store reviews"),
         ("Survived cleaning and de-duplication", int(funnel.scored),
          "boilerplate, duplicates and empty text removed"),
         ("Bear on saving or buying a fashion item", int(funnel.relevant),
          "wishlist behaviour of ANY kind, including saving with no intention of "
          "buying — see the rule below"),
         ("Analysed", denom,
          "after dropping five subreddits that produced almost no relevant records")]
st.plotly_chart(
    charts.attrition([t for t, _, _ in steps], [n for _, n, _ in steps],
                     title="Records surviving each cut"),
    width="stretch")
for t, n, why in steps:
    st.html(f"<div style='font-size:.95rem;margin:.15rem 0'><b>{n:,}</b> — {t}  ·  <span style='color:#8a8a8a;font-size:.85rem'>{why}"
                f"</span></div>")
st.caption(f"These are **records, not people**: the {denom:,} analysed records were "
           f"written by {int(funnel.authors):,} distinct authors, and that second number is "
           "carried alongside every count in this app — 200 records from 12 people is a much "
           "weaker claim than 200 from 180. The gap between the second and third bars is the "
           "filter doing its job: most public conversation about a shopping app is about "
           "delivery and refunds, not about deciding.")

# The single most misread thing on the page, so it is stated rather than left
# to be inferred from a denominator: the funnel and the stage split do NOT
# share a population. Only the records that survived the relevance rule were
# ever sent to the classifier, so every number in sections 4 to 7 sits inside
# the last bar above and none of them can speak for the other 7,440.
st.info(
    f"**Everything after this point lives inside the last bar.** Only the "
    f"**{denom:,}** records that survived the relevance rule were sent to the classifier, "
    f"so only they carry a step and a barrier. The "
    f"**{int(funnel.scored) - int(funnel.relevant):,}** records the rule rejected were read "
    "and reasoned about one by one — the reason is stored against each of them and browsable "
    "on **Data Bank** — but they were never assigned a step, and nothing in sections 4 to 7 "
    "speaks for them.\n\n"
    "So the shape of the argument from here is: **these "
    f"{denom:,} records → which of the four steps they sit in → who the people "
    "in that step are → what to fix for them.**", icon="🎯")

# "Why only people who meant to buy?" is the first question a reader asks of a
# funnel this narrow, and the answer is that it is NOT that narrow — the rule
# admits saving with no purchase intent on purpose, because a wishlist that was
# never a shopping list is one of the answers, not a record to discard. The
# engine can only report how much of that there is if it kept those records in
# the first place. Stating this here rather than leaving it to section 6, where
# the two non-buying groups get sized and set aside.
with st.expander("“Why only people who meant to buy?” — the rule, in full"):
    st.markdown(
        "**It is not restricted to people who meant to buy.** The relevance rule admits "
        "**wishlist and saved-item behaviour of any kind**, and says so explicitly, "
        "including *collecting or browsing with no purchase intent at all*. Saving for "
        "inspiration, saving as a taste archive, saving something you never intended to "
        "buy — those are kept, because **“they never meant to buy it” is one of the "
        "answers to the research question**, and an engine that filtered those records "
        "out would have quietly assumed its own conclusion and then reported it back.\n\n"
        "That is exactly what makes the numbers in section 6 possible: **saving for "
        "reference is measured at 126 records and intent that never existed at 21** — "
        "roughly one saved item in eight is not a conversion problem at all. Neither "
        "figure could exist if the filter had kept only shoppers with intent.")
    a, b = st.columns(2)
    a.markdown(
        "**Kept**\n\n"
        "- wishlist and saved-item behaviour of any kind\n"
        "- collecting or browsing with **no** purchase intent\n"
        "- fit, size, fabric, colour and styling doubt\n"
        "- wanting other buyers' photos or reviews first\n"
        "- price doubt, waiting for a sale, timing\n"
        "- needing someone else's approval\n"
        "- leaving the platform to check something\n"
        "- cart and checkout abandonment\n"
        "- a past bad experience *cited as present hesitation*")
    b.markdown(
        "**Dropped**\n\n"
        "- delivery delays, couriers, order status\n"
        "- refunds, cancellations, customer service\n"
        "- app crashes, login and payment-gateway bugs\n"
        "- post-purchase praise with nothing decision-bearing\n"
        "  (*“lovely kurta, five stars”*)\n"
        "- promotional and spam content\n"
        "- **any non-fashion category** — saving laptops, fridges or\n"
        "  groceries is out, however closely it mirrors the pattern")
    st.caption(
        "The category rule is the aggressive one, and it is deliberate: this project is "
        "about *fashion-specific* uncertainty — fit, fabric, sizing, whether it suits you "
        "— which has no equivalent for a fridge. It is also the reason the ranking is "
        "conditional on the rule rather than true of wishlists in general.")
    st.warning(
        "**The rule's known weakness runs in exactly this direction.** A human reviewer "
        "re-judged 30 randomly drawn records and disagreed on 11 — and **every single one "
        "was a record the filter had rejected.** All 9 it accepted were confirmed. So what "
        "is in this corpus belongs here, and the open question is what the rule threw away. "
        "It is recorded as a limitation rather than repaired, because repairing it means "
        "re-running the analysis.", icon="⚠️")

with st.expander("The two checks that could have invalidated everything downstream"):
    z = prev[prev["code"] == "Z-99"]
    gold = db.query("SELECT code, gold_n, kappa, verdict FROM analysis_gold_agreement "
                    "WHERE measurable = 1 ORDER BY kappa DESC")
    a, b = st.columns(2)
    if not z.empty:
        a.metric("Relevant but matching no pre-registered barrier",
                 f"{float(z['share'].iloc[0]):.1%}")
        a.caption("The honesty valve. If this were large, the frozen list would be missing "
                  "something real and the whole ranking would be suspect. It is not — but "
                  "the residual was still clustered separately and read, and it turned out "
                  "to be mostly deal-hunting and off-topic chat.")
    if not gold.empty:
        ok = int((gold["verdict"] == "reliable").sum())
        b.metric("Barriers whose agreement with a human coder clears the bar",
                 f"{ok} of {len(gold)}")
        b.caption("A hand-labelled gold set was built blind and the pipeline scored "
                  "against it. Most barriers appear too rarely in it to measure at all. "
                  "This is reported as a limitation rather than tuned away, and every "
                  "claim resting on an unreliable barrier says so on the page.")
        g = gold.copy()
        g["barrier"] = g["code"].map(S.voice)
        g["agreement (κ)"] = g["kappa"].map(lambda v: f"{float(v):.2f}")
        st.dataframe(g[["barrier", "gold_n", "agreement (κ)", "verdict"]].rename(
            columns={"gold_n": "hand-labelled records"}), width="stretch", hide_index=True)

# ============================================ 4. which step is it about
st.header("4 · Which of the four steps the conversation is actually about")
st.caption(
    f"This is the first real narrowing decision, and it is the one most likely to be an "
    f"artefact. Each of the **{denom:,}** records was classified against the "
    "frozen list, and the width below is how much of *that* conversation each step carries. "
    "A record can raise barriers at more than one step, which is why the segments below "
    "add to more than the bar does.")

rows = [{"n": stage_n.get(s, 0), "title": S.stage_title(s), "colour": S.STAGE_COLOUR[s]}
        for s in S.STAGE_ORDER]
st.plotly_chart(charts.journey(rows), width="stretch")

lead = max(S.STAGE_ORDER, key=lambda s: stage_n.get(s, 0))
st.markdown(f"**Step 3 — {S.stage_title(lead)} — carries "
            f"{stage_n.get(lead, 0):,} of the {sum(stage_n.get(s, 0) for s in S.STAGE_ORDER):,} "
            f"coded mentions.** It is not close.")

inv = db.query("SELECT * FROM analysis_stage_inversion WHERE inversion_factor IS NOT NULL "
               "ORDER BY inversion_factor")
st.markdown("#### But a loud step is not the same as a big one")
st.caption(
    "Two of the four steps are quiet **by construction**, not because they are small. "
    "Forgetting a wishlist produces no complaint, and nobody posts about a list being hard "
    "to scroll — they just search for the item again. So the size of a step is the wrong "
    "thing to trust, and picking the loudest one on volume alone would be the single "
    "easiest way to get this project wrong.\n\n"
    "Rather than accept the ranking or discard it, the engine asks how *wrong* the counts "
    "would have to be for the answer to change: **the multiplier by which each quiet step "
    "would have to be under-reported to overtake the leader.** Roughly 2–3× is plausible "
    "for a silent barrier. Beyond that, the choice is safe.")
if not inv.empty:
    icols = st.columns(len(inv))
    for col, (_, r) in zip(icols, inv.iterrows()):
        s = str(r["stage"])
        col.metric(f"{S.stage_title(s)} would need",
                   f"{float(r['inversion_factor']):.1f}×")
        col.caption(f"under-reporting to overtake step 3 — "
                    f"{'plausible, treat as fragile' if int(r['fragile']) else 'not plausible'}")
    st.success(
        f"The tightest of these is **{float(inv.iloc[0]['inversion_factor']):.1f}×**, "
        "comfortably past what silence can explain. **Step 3, deciding on the item, is "
        "where the engine goes to work** — and that conclusion survives the objection "
        "that the corpus cannot hear the quiet steps.", icon="✅")

# ================================================== 5. segmenting inside it
st.header("5 · Who, inside that step — segmented on behaviour, not motive")
st.info(
    "**An earlier segmentation was measured and thrown out.** It asked *why did you save "
    "it?* — a motivation public text almost never states. Coverage reached 6.6%, and the "
    "labels that did appear were overwhelmingly one type, because collecting behaviour "
    "gets said out loud while urgency does not. That segmentation was not merely thin, it "
    "was biased. It is recorded here because the replacement only makes sense as an answer "
    "to it.", icon="🔁")

st.markdown("#### Three structural questions, all of them already answered by the classifier")
qs = [("Intent", "Is there any intent to buy at all?", "no · lapsed · yes"),
      ("Time to purchase", "Soon, or waiting on a price, a restock, an occasion?",
       "soon · later"),
      ("Decision", "Have they decided — or is a doubt still unresolved?", "decided · not")]
qcards = []
for i, (short, q, ans) in enumerate(qs, 1):
    qcards.append(
        f"<div style='flex:1;min-width:180px;border:1px solid #4a4a4a;border-radius:8px;"
        f"padding:.6rem .7rem'>"
        f"<div style='font-size:.68rem;letter-spacing:.1em;color:#8a8a8a'>QUESTION {i}</div>"
        f"<div style='font-weight:700;margin:.1rem 0'>{short}</div>"
        f"<div style='font-size:.85rem;color:#9a9a9a;line-height:1.35'>{q}</div>"
        f"<div style='font-size:.75rem;color:{S.STAGE_COLOUR['C']};margin-top:.45rem'>"
        f"{ans}</div></div>")
st.html("<div style='display:flex;flex-wrap:wrap;gap:.5rem;margin:.5rem 0 .8rem'>"
        + arrow.join(qcards) + "</div>")

st.markdown(
    "The third question is the join to step 3, and it is the whole idea: **a voiced doubt "
    "*is* an undecided decision.** \"Have they decided\" is operationalised as the absence "
    "of any unresolved item-level doubt — exactly the thing the classification pass already "
    "found. So these groups are a **re-cut of the same evidence, not a second opinion**, "
    "which is why coverage is 100% where the motivation-based version reached 6.6%.")

seg = db.query("""SELECT segment_id, segment_name, count(*) AS n FROM segments_v2
                  GROUP BY segment_id, segment_name ORDER BY segment_id""")
DERIV = {1: ("no intent", "—", "—"), 2: ("lapsed", "—", "—"),
         3: ("yes", "soon", "decided"), 4: ("yes", "soon", "NOT decided"),
         5: ("yes", "later", "decided"), 6: ("yes", "later", "not decided")}
if not seg.empty:
    d = seg.copy()
    d["group"] = d["segment_id"].astype(int).map(
        lambda i: ("⭐ " if i == F.TARGET_SEGMENT else "") + S.segment_label(i))
    d["intent"] = d["segment_id"].map(lambda i: DERIV[int(i)][0])
    d["time to purchase"] = d["segment_id"].map(lambda i: DERIV[int(i)][1])
    d["decided?"] = d["segment_id"].map(lambda i: DERIV[int(i)][2])
    d["share"] = (d["n"] / denom).map(lambda v: f"{v:.1%}")
    d["what they are"] = d["segment_id"].map(lambda i: S.segment_blurb(int(i)))
    st.dataframe(d[["group", "intent", "time to purchase", "decided?", "n", "share",
                    "what they are"]].rename(columns={"n": "people"}),
                 width="stretch", hide_index=True)
    st.caption("Six groups fall out of three yes/no questions. Nobody was assigned by "
               "hand and nothing was inferred about a motive that was never stated.")

# ============================================== 6. why Stuck Deciders
st.header("6 · Why the target is Stuck Deciders")

addr = db.query("SELECT * FROM analysis_addressable").set_index("bucket")
st.markdown("#### First, two groups are counted and then set aside")
st.caption(
    "Not everyone in the corpus is a conversion problem, and treating them as one would "
    "quietly inflate every number that follows. Both exclusions are **measured before they "
    "are removed**, because how big they are is itself one of the findings.")
acols = st.columns(4)
for col, bucket, plain in zip(
        acols, ["corpus", "c9_no_live_intent", "collectors", "addressable"],
        ["Everyone we heard from", "Never meant to buy", "Saving for reference",
         "Actually winnable"]):
    if bucket in addr.index:
        r = addr.loc[bucket]
        col.metric(plain, f"{int(r['n']):,}", help=str(r["reason"]))
        col.caption(f"{float(r['share_of_corpus']):.0%} of everyone we heard from")
if "overlap" in addr.index:
    st.caption(f"The two exclusions overlap by {int(addr.loc['overlap','n'])} records, so "
               "they are not additive. Converting people who save for reference would mean "
               "optimising against the user — that is a product decision, not a data one, "
               "and it is stated rather than assumed.")

rec = db.query("SELECT * FROM analysis_segment_recommendation ORDER BY score DESC")
if not rec.empty:
    st.markdown("#### Then the five remaining groups are compared on four things")
    st.caption(
        "Size alone would be a lazy answer. A group is worth targeting only if it is also "
        "**reachable without a discount** — the assignment forbids monetary remedies — "
        "**distinctive**, so that a fix aimed at it is not merely a fix for everyone, and "
        "**evidenced well enough that the engine can say what specifically stops it.** "
        "That last one is the quiet disqualifier, and it is the column most easily skipped "
        "over: two of these groups have only a *single* barrier cell reaching the "
        "30-record floor, so anything said about *what* blocks them is directional at best.")

    # The comparison columns are parsed out of the rationale string the pipeline
    # wrote rather than recomputed here: this page must not be able to disagree
    # with the synthesis step about its own recommendation.
    r = rec.copy()
    r["group"] = r["segment_id"].astype(int).map(
        lambda i: ("⭐ " if i == F.TARGET_SEGMENT else "") + S.segment_label(i))
    r["how big"] = r["n"].astype(int)
    r["% of winnable"] = r["share"].map(lambda v: f"{float(v):.1%}")
    r["fixable without a discount"] = r["rationale"].str.extract(
        r"(\d+)% of its coded barriers are solvable")[0].map(
        lambda v: f"{v}%" if pd.notna(v) else "—")
    r["sharpest barrier vs everyone"] = r["rationale"].str.extract(
        r"at ([\d.]+)x the corpus rate")[0].map(
        lambda v: f"{float(v):.1f}×" if pd.notna(v) else "—")
    r["barriers we can actually rank"] = r["rankable_cells"].astype(int)
    r["judged on"] = r["basis"]
    st.dataframe(
        r[["group", "how big", "% of winnable", "fixable without a discount",
           "sharpest barrier vs everyone", "barriers we can actually rank",
           "judged on", "score"]],
        width="stretch", hide_index=True,
        column_config={"score": st.column_config.ProgressColumn(
            "score", min_value=0.0, max_value=1.0, format="%.2f")})
    st.caption("`judged on` records which matrix actually carried the judgement. A group "
               "read at stage level must never be quoted later as if it had been ranked "
               "barrier by barrier.")

    win = rec[rec["recommended"] == 1]
    if not win.empty:
        w = win.iloc[0]
        st.success(
            f"**{S.segment_label(int(w['segment_id']))} — {int(w['n'])} people, "
            f"{float(w['share']):.1%} of the winnable population.** They want the item, "
            "they want it soon, and something specific and nameable is in the way. Every "
            "barrier they raise is fixable without a monetary incentive, and six of their "
            "barrier cells clear the evidence floor — enough to say **what** to build, "
            "not merely **who** for.", icon="🎯")
        st.warning(
            "**They do not win every column, and the honest reading matters here.** Lapsed "
            "Intenders are far *sharper*: their most distinctive barrier runs at 11.4× "
            "the corpus rate against 2.2× for Stuck Deciders, so on distinctiveness "
            "alone they would lead. They lose because they are 78 people with **one** "
            "rankable barrier cell — the engine can say who they are and not what to "
            "build for them. Stuck Deciders win on the *combination*: the largest winnable "
            "group, wholly addressable without a discount, and the only one evidenced "
            "deeply enough to act on. A sharper group that cannot be acted on is a research "
            "lead rather than a target, and it is carried into the interview guide as one.",
            icon="⚖️")

        dist = json.loads(w["distinctive"] or "[]")
        if dist:
            st.markdown("**What is distinctive about them, once they are chosen**")
            dd = pd.DataFrame(dist)
            dd["what the shopper is thinking"] = dd["code"].map(S.voice)
            dd["people"] = dd["n"].astype(int)
            dd["share of the group"] = dd["share"].map(lambda v: f"{float(v):.0%}")
            dd["vs everyone else"] = dd["lift"].map(lambda v: f"{float(v):.2f}×")
            st.dataframe(dd[["what the shopper is thinking", "people",
                             "share of the group", "vs everyone else"]],
                         width="stretch", hide_index=True)
            st.info(
                "**Read that lift with one caveat, stated here rather than buried.** The "
                "groups are *derived* from the classification — \"not decided\" means "
                "an unresolved item-level doubt — so item-level doubts are bound to "
                "concentrate here. Part of this lift is the derivation rule, not a "
                "measurement. It still ranks the barriers against each other usefully; it "
                "cannot on its own prove the group is special. The ranking in the next "
                "section does not depend on it: set the *segment fit* weight to zero on "
                "the Insights page and the order holds.", icon="🔁")

# ================================================ 7. the opportunity score
st.header("7 · What to solve first — and what the score is made of")
opp = db.query("SELECT * FROM analysis_opportunity WHERE rank IS NOT NULL ORDER BY rank")
COMPONENTS = {
    "prevalence": "How often it comes up",
    "intensity": "How hard people work around it",
    "defer_share": "How often intent survives",
    "solvable_without_money": "Fixable without a discount",
    "evidence_strength": "How well-supported",
    "segment_fit": "How specific to Stuck Deciders",
}
st.caption(
    "A ranking by volume would just re-report which barrier is easiest to complain about. "
    "The opportunity score is the **average of six stored components**, each on a 0–1 "
    "scale — so every bar below can be taken apart into the six things that earned it, and "
    "the interesting reading is almost always in the slices rather than the total.")

WHY = {
    "prevalence": "how much of the winnable conversation raises it, scaled against the "
                  "largest barrier",
    "intensity": "how often people spend real effort working around it — ordering two "
                 "sizes, hunting for buyer photos. Stronger evidence than complaint "
                 "volume, which mostly measures how annoying something is to talk about",
    "defer_share": "how often the intent survived the barrier. A deferred shopper is "
                   "winnable; someone whose intent was destroyed mostly is not",
    "solvable_without_money": "the assignment forbids discounts, coupons and cashback. A "
                              "barrier that can only be solved by dropping the price "
                              "scores zero here",
    "evidence_strength": "how many of the four sources carry it, how often people name "
                         "their own unblock, and how confident the classifier was",
    "segment_fit": "how concentrated it is in the target group rather than spread evenly",
}
wcols = st.columns(3)
for i, (comp, label) in enumerate(COMPONENTS.items()):
    with wcols[i % 3]:
        st.html(f"<div style='border-left:3px solid {charts.PALETTE[i]};"
                    f"padding-left:.55rem;margin-bottom:.7rem'>"
                    f"<b style='font-size:.92rem'>{label}</b><br>"
                    f"<span style='font-size:.82rem;color:#9a9a9a;line-height:1.35'>"
                    f"{WHY[comp]}</span></div>")

if not opp.empty:
    top = opp.head(8).copy()
    top["label"] = top["code"].map(S.chart_label)
    st.plotly_chart(
        charts.contribution(top.iloc[::-1], "label", COMPONENTS,
                            title="The opportunity score taken apart — top 8 barriers",
                            height=440),
        width="stretch")
    st.caption("Bar length is the score; each colour is one component's contribution to "
               "it. Barriers under 30 records are scored but never ranked — a handful of "
               "comments cannot settle which problem is bigger.")

    lead = opp.iloc[0]
    sens = db.query("SELECT * FROM analysis_weight_sensitivity ORDER BY top_share DESC")
    a, b = st.columns([1, 2])
    a.metric("Top-ranked barrier scores", f"{float(lead['score']):.2f}")
    a.caption(f"“{S.voice(lead['code'])}” · {int(lead['n'])} records")
    if not sens.empty:
        t = sens.iloc[0]
        b.metric("Holds first place in", f"{float(t['top_share']):.1%}")
        b.caption(f"of {int(t['n_draws']):,} weightings perturbed ±"
                  f"{float(t['perturbation']):.0%} — the six weights were shaken a "
                  "thousand times and the winner barely moved")
        st.success(
            "**The ranking is not an artefact of the weights we happened to choose.** "
            "That is a far stronger claim than a single asserted ranking, and it is why "
            "the weights are exposed as sliders on the Insights page: a reader who can "
            "move them and watch the order hold has been given the answer before asking "
            "for it.", icon="✅")

    # The one thing a reader would otherwise have to cross-reference three
    # sections to notice: the winner is robust to the WEIGHTS and rests on a
    # code the human coder only weakly agreed with. Both are true, and putting
    # them next to each other is the difference between a report and a claim.
    lead_k = db.query("SELECT kappa, verdict FROM analysis_gold_agreement "
                      "WHERE code = ? AND measurable = 1", (str(lead["code"]),))
    if not lead_k.empty and str(lead_k.iloc[0]["verdict"]) != "reliable":
        st.warning(
            f"**Robust to the weights is not the same as robust to the labelling, and the "
            f"winner is only one of those.** “{S.voice(lead['code'])}” agrees with the "
            f"human coder at κ {float(lead_k.iloc[0]['kappa']):.2f} — "
            f"*{lead_k.iloc[0]['verdict']}*, short of the 0.60 bar — on the hand-labelled "
            "records where agreement could be measured at all. Its **rank** survives a "
            "thousand reweightings; its **boundary** against neighbouring doubts does not "
            "yet survive a second reader. That is the first thing the interviews are for, "
            "and it is why the recommendation is a starting point for primary research "
            "rather than a conclusion.", icon="⚖️")

    price = opp[opp["code"] == "C6"]
    if not price.empty:
        p = price.iloc[0]
        st.info(
            f"**The clearest case of the score doing visible work: price.** "
            f"“{S.voice('C6')}” is the **second-largest barrier by volume** "
            f"({int(p['n'])} records) and it ranks **{int(p['rank'])}th**. Its bar above "
            "carries the second-widest prevalence slice of the eight and then loses on "
            f"exactly two components: it enters at **half weight on solvability** "
            f"({float(p['solvable_without_money']):.1f}) because the assignment forbids "
            f"discounts, coupons and cashback, and it scores "
            f"**{float(p['segment_fit']):.1f} on fit to the target group** because price "
            "talk is spread evenly across every group rather than concentrating in Stuck "
            "Deciders. That is a statement about what this project is allowed to build, "
            "**not** a claim that price does not matter — it has to be resolved into "
            "transparency, anchoring and timing, or reported as out of scope.", icon="💰")

# ================================================ 8. what happens after
st.header("8 · What the engine does after it has an answer")
st.caption("A ranking that nothing could disprove is not a finding. Four passes exist "
           "purely to attack the result the previous sections produced.")

k1, k2 = st.columns(2)
with k1:
    with st.container(border=True):
        st.markdown("**An independent method has to find the same shape**")
        clus = db.query("""SELECT cl.label, cl.size, cc.code, cc.n
                           FROM analysis_cluster_code cc JOIN cluster_labels cl
                             ON cl.cluster_id = cc.cluster_id AND cl.space = cc.space
                           WHERE cc.space = 'all' AND cc.code <> 'Z-99'
                           ORDER BY cc.n DESC LIMIT 1""")
        if not clus.empty:
            c = clus.iloc[0]
            st.markdown(
                f"The records were also clustered on meaning alone and each cluster named "
                f"**blind to the barrier list**. The largest cluster came back as "
                f"*“{str(c['label']).strip()}”* — {int(c['size'])} records — and it holds "
                f"{int(c['n'])} of the records the classifier had independently labelled "
                f"“{S.voice(c['code'])}”.")
            st.caption("Two methods that share no vocabulary arriving at the same group is "
                       "the strongest corroboration available here. It also produced the "
                       "headline insight: two barriers the codebook treats as separate "
                       "turn out to be one event.")
    with st.container(border=True):
        st.markdown("**Barriers that travel together are one problem, not two**")
        co = db.query("""SELECT code_a, code_b, n_joint, lift FROM analysis_cooccurrence
                         WHERE min_support_met = 1 AND code_a <> 'Z-99'
                           AND code_b <> 'Z-99' AND code_a IN ('C1') ORDER BY lift DESC
                         LIMIT 1""")
        if not co.empty:
            x = co.iloc[0]
            st.markdown(f"*“{S.voice(x['code_a'])}”* and *“{S.voice(x['code_b'])}”* appear "
                        f"in the same record **{float(x['lift']):.1f}× more often than "
                        f"chance** ({int(x['n_joint'])} records).")
            st.caption("Ranked by how *surprising* the pairing is, not how often it "
                       "happens — two common barriers co-occur a lot by chance, and that "
                       "is not evidence they are connected. One compound problem with one "
                       "fix is a different roadmap from two separate ones.")

with k2:
    with st.container(border=True):
        st.markdown("**Did it only rediscover what we already believed?**")
        ins = db.query("SELECT count(*) AS n, sum(novelty) AS novel FROM insights")
        if not ins.empty and int(ins.iloc[0]["n"]):
            st.markdown(
                f"Each of the {int(ins.iloc[0]['n'])} insights was embedded against all 28 "
                f"pre-registered hypotheses and scored for similarity; the cut-off was "
                f"**calibrated against a control set of deliberate restatements** rather "
                f"than chosen. **{int(ins.iloc[0]['novel'] or 0)} survived by hand as "
                f"genuinely new.**")
            st.caption("An engine that returns only what its author already believed did "
                       "not mine anything — it confirmed a hunch at some expense.")
    with st.container(border=True):
        st.markdown("**Everything ends in something that can be killed**")
        hyp = db.query("SELECT count(*) AS n FROM hypotheses")
        n_h = int(hyp.iloc[0]["n"]) if not hyp.empty else 0
        st.markdown(f"{n_h} hypotheses, each a causal claim carrying **what would disprove "
                    "it** and **what already argues against it** — and each one generating "
                    "the interview questions and survey items that would settle it.")
        st.caption("The engine's output is not a conclusion. It is a ranked, evidenced "
                   "starting point for primary research, plus the instruments to run it. "
                   "Download them from the last tab on **Insights**.")

st.divider()

# ------------------------------------------------------- limits and provenance
with st.expander("What this engine cannot tell you"):
    st.markdown("""
- **It is not a funnel.** No user-level data exists here. Nothing on any page is a drop-off
  or conversion rate, however much it may look like one — every share is a share of
  *conversation*.
- **Quiet barriers are under-counted by construction.** Forgetting produces no complaint.
  Section 4 above puts a number on how far that could throw the ranking rather than
  waving it away.
- **The relevance rule is narrow on purpose**, and a human reviewer disagreed with it on 11
  of 30 randomly drawn records — every one of them a record the filter had *rejected*, and
  all 9 it accepted were confirmed. What is in this corpus belongs here; the open question
  is what is missing. Recorded as a limitation rather than repaired, because fixing it
  would mean re-running the analysis.
- **Agreement with a human coder clears its threshold for only 2 of the 5 barriers** with
  enough hand-labelled data to measure it. The least reliable of them carries the headline
  insight, and every claim resting on it says so.
- **Only about a third of the corpus is Myntra-specific.** Platform-mechanical barriers are
  ranked on their Myntra-specific count, not the pooled one.
- **It is a research instrument, not a Myntra product**, built on public data only.
""")

with st.expander("Why you should believe any of it"):
    st.markdown("""
**The barrier list was frozen before a single record was read**, with a version string and a
date in the repository. Where a record fits nothing on the list it goes to a residual
bucket, and the size of that bucket is reported — because if it were large, the list would
be wrong.

**Every quote is verified word-for-word** against the record it came from. A quote that is
not an exact substring is not evidence and is never shown, anywhere in the app.

**Every count carries how many *different people* it came from.** 200 records from 12 people
is a much weaker claim than 200 from 180.

**Nothing is deleted quietly.** Every excluded record is logged with its reason and stays
browsable on the Data Bank page.

**Measurements beat predictions, including our own.** A pre-filter was removed after it was
measured throwing away 23% of relevant records to save $2.49. A model-tier decision was
reversed after testing it on hand-labelled boundary cases. Both are written up with the
numbers that overturned them.

**The app computes nothing.** Every figure on every page is read from a table the offline
pipeline wrote, which is why the charts and the chatbot cannot disagree with each other and
why numbers do not move between page loads.
""")

with st.sidebar:
    frozen = ROOT / "codebook" / "FROZEN.json"
    if frozen.exists():
        fz = json.loads(frozen.read_text())
        st.caption(f"Barrier list **{fz['version_string']}**  \n{fz['n_scored_codes']} "
                   f"barriers, frozen {fz['frozen_at'][:10]} — before any scoring")
    st.caption("**Phases**  \nP0 foundation ✅  \nP1 data bank ✅  \nP2 analysis ✅  \n"
               "P3 insights ✅  \nP4 ask ✅  \nP5 release ⬜")

st.divider()
st.caption("Public data only · authors pseudonymised · no personal information in outputs.")
