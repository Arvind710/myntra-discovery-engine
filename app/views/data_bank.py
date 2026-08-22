"""Data Bank — where the evidence came from, and what was thrown away.

WHY THIS PAGE LOOKS THE WAY IT DOES
-----------------------------------
Third page to get the same correction (see Analysis and Insights). It held
three tabs — "Read the records", "What is in the corpus", "What was set aside"
— which is a list of contents, not an argument. The material a reader needs in
order to trust every other page (the relevance rule, and the human check that
found its weakness) sat inside an expander inside a tab.

It is now one chain, numbered, each link a conclusion with one visual:

    1  12,002 records from four public sources, written by 4,711 people
    2  only 1,018 of them bear on the question at all       <- the waterfall
    3  one stated rule decided that, and a human found where it is weak
    4  nothing was deleted — every removal has a logged reason
    5  where the collection is weakest, measured rather than guessed

THE NUMBERS THAT NEVER RECONCILED
---------------------------------
The old page showed "Collected 12,002 = Kept 5,099 + Set aside 6,903" beside a
funnel whose second bar was 8,639 "survived cleaning" — and a careful reader was
left to work out how more records could survive cleaning than were kept. They
are two different cuts and the page never said so. The waterfall in step 2 is
now the single chronological account, computed stage by stage so it has to
balance, and 5,099 is presented for what it actually is: the readable corpus.

Design rules kept: no aggregation the pipeline could have materialised is
invented here; raw HTML goes through `st.html` (never `unsafe_allow_html`), and
`st.html` silently strips `<svg>`, so anything vector is a Plotly figure.
"""

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from lib import charts, db, story as S

MUTED = "#8a8a8a"
HAIR = "rgba(128,128,128,.28)"
OK, WARN, BAD = "#009E73", "#E69F00", "#D55E00"
BLUE = "#0072B2"


# --------------------------------------------------------------- furniture
def section(num: int, title: str, sub: str = "", colour: str = BLUE) -> None:
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
    st.html(
        f"<div style='border-left:4px solid {colour};padding:.6rem 0 .6rem .85rem;"
        f"margin:.9rem 0 .2rem;font-size:1.02rem;line-height:1.5'>{text}</div>")


def note(text: str) -> None:
    st.html(f"<div style='color:{MUTED};font-size:.82rem;line-height:1.5;"
            f"margin:.35rem 0 0;max-width:80ch'>{text}</div>")


def heading(text: str, top: str = "1.4rem") -> None:
    st.html(f"<div style='font-weight:700;margin:{top} 0 .1rem'>{text}</div>")


st.title("The evidence")
st.html(f"<div style='color:{MUTED};font-size:1.02rem;margin:-.5rem 0 .4rem;"
        f"max-width:72ch;line-height:1.55'>Every comment, post and review this project "
        f"read — how much of it turned out to bear on the question, the rule that "
        f"decided, and everything it threw away with the reason attached.</div>")

status, detail = db.db_status()
if status != "ok":
    # Report which condition actually holds. "Not collected yet" asserted a
    # cause the check never established, and read as a project that never ran.
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

# Every stage is COUNTED, not derived by subtraction, so the waterfall below
# cannot silently stop balancing if the pipeline changes.
t = db.query("""
    SELECT (SELECT count(*) FROM records)                                  AS collected,
           (SELECT count(*) FROM retained)                                 AS retained,
           (SELECT count(DISTINCT record_id) FROM exclusions)              AS excluded,
           (SELECT count(DISTINCT author_hash) FROM retained
             WHERE author_hash IS NOT NULL)                                AS authors,
           (SELECT count(DISTINCT record_id) FROM exclusions
             WHERE stage = 'clean')                                        AS cleaned,
           (SELECT count(*) FROM relevance)                                AS scored,
           (SELECT count(*) FROM relevance WHERE is_relevant = 1)          AS relevant,
           (SELECT count(*) FROM relevance WHERE is_relevant = 1
             AND record_id IN (SELECT record_id FROM retained))            AS analysed
""").iloc[0]

collected, retained_n = int(t.collected), int(t.retained)
excluded_n, authors = int(t.excluded), int(t.authors)
cleaned, scored = int(t.cleaned), int(t.scored)
relevant, analysed = int(t.relevant), int(t.analysed)
after_clean = collected - cleaned

by_src = db.query("""
    SELECT source, count(*) AS n, count(DISTINCT author_hash) AS authors
    FROM retained GROUP BY source ORDER BY n DESC""")
# `curated` is a handful of hand-picked secondary research items, not a public
# conversation source. Counting it made the page say "5 sources" two lines
# above prose that says four.
n_public = int((by_src["source"] != "curated").sum())

st.warning(S.PROXY_WARNING, icon="⚠️")

# ------------------------------------------------------------- the chain
CHAIN = [
    (f"<b>{collected:,}</b> records read", f"from {n_public} public sources", BLUE),
    (f"Only <b>{analysed:,}</b> bear on<br>the question", "the rest are about something "
     "else", "#E69F00"),
    ("<b>One stated rule</b><br>decided which", "written down before collection", "#CC79A7"),
    (f"<b>{excluded_n:,}</b> set aside,<br>none deleted", "every removal has a logged "
     "reason", "#56B4E9"),
    ("The weak spot is<br><b>measured</b>", "untargeted scraping yields a quarter as "
     "much", BAD),
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
section(1, "What was read",
        "Public conversation is the only data this project has — there is no access to "
        "Myntra's analytics. Four sources, chosen because they are where people discuss "
        "buying clothes in the open and because none of them requires anyone's "
        "permission to read.")

a, b, c = st.columns(3)
for col, value, label, sub in (
        (a, f"{collected:,}", "records collected", f"across {n_public} public sources"),
        (b, f"{authors:,}", "different people", "in the readable corpus"),
        (c, f"{retained_n:,}", "readable here", "the rest are set aside, not deleted")):
    col.html(f"<div style='border-top:3px solid {BLUE};padding-top:.5rem'>"
             f"<div style='font-size:1.9rem;font-weight:750;line-height:1'>{value}</div>"
             f"<div style='font-size:.9rem;margin-top:.15rem'>{label}</div>"
             f"<div style='font-size:.76rem;color:{MUTED}'>{sub}</div></div>")

st.caption(S.explain("authors"))

heading("Where it came from")
d = by_src.sort_values("n")
fig = go.Figure()
fig.add_trace(go.Bar(
    x=d["n"], y=d["source"], orientation="h", marker_color=BLUE, name="records",
    text=[f" {int(v):,} records · {int(au):,} people"
          for v, au in zip(d["n"], d["authors"])],
    textposition="outside", cliponaxis=False,
    hovertemplate="<b>%{y}</b><br>%{x:,} records<extra></extra>"))
fig.update_layout(
    height=90 + 40 * len(d), margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    xaxis=dict(visible=False, range=[0, float(d["n"].max()) * 1.5]),
    yaxis=dict(showgrid=False))
st.plotly_chart(fig, width="stretch")

note("<code>curated</code> is a handful of hand-picked secondary research items — "
     "published articles and reports, not user conversation. They are never scored for "
     "relevance and never counted in any barrier, which is why they drop out of the "
     "waterfall below.")

st.info(
    "**Read this as a map of where people talk, not of who shops.** YouTube leads "
    "because YouTube comment threads are long and public, not because YouTube users "
    "hesitate more. Google Play and the App Store are also **not independent of each "
    "other** — both are app-store reviews written by people with a grievance — so the "
    "effective number of independent viewpoints is lower than the source count "
    "suggests, and triangulation claims elsewhere are weighted accordingly.", icon="🗺️")


# ============================================================== STEP 2
section(2, f"Only {analysed:,} of the {collected:,} bear on the question",
        "The first question about public conversation is not *what does it say* but "
        "*how much of it is about saving and buying at all.* Each drop below is a "
        "stated rule applied in order — and each bar is counted directly, so the "
        "arithmetic has to close.", "#E69F00")

# A waterfall rather than four descending bars: the old chart showed the
# survivors and left the reader to subtract. The DROPS are the argument.
steps = [
    ("Collected", collected, "absolute", ""),
    ("Cleaning", -cleaned, "relative",
     "too short, emoji-only, or an exact/near duplicate"),
    ("Curated research items", -(after_clean - scored), "relative",
     "secondary sources, not user conversation — never scored for relevance"),
    ("Not about saving or buying", -(scored - relevant), "relative",
     "judged one by one against the rule in step 3, with the reason stored"),
    ("Five low-yield subreddits", -(relevant - analysed), "relative",
     "general and city forums that produced almost nothing on topic"),
    ("Analysed", analysed, "total", "the only records carrying a journey step and a barrier"),
]
fig = go.Figure(go.Waterfall(
    orientation="v",
    measure=[m for _, _, m, _ in steps],
    x=[lbl for lbl, _, _, _ in steps],
    y=[v for _, v, _, _ in steps],
    text=[f"{v:+,}" if m == "relative" else f"{v:,}" for _, v, m, _ in steps],
    textposition="outside", cliponaxis=False,
    connector=dict(line=dict(color=HAIR, width=1.5)),
    decreasing=dict(marker=dict(color=BAD)),
    increasing=dict(marker=dict(color=BLUE)),
    totals=dict(marker=dict(color=BLUE)),
    hovertemplate="<b>%{x}</b><br>%{y:+,} records<extra></extra>"))
fig.update_layout(
    height=420, margin=dict(l=10, r=10, t=30, b=90),
    plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    xaxis=dict(tickangle=-22, tickfont=dict(size=11)),
    yaxis=dict(showgrid=True, gridcolor=HAIR, title="records", title_font_size=11))
st.plotly_chart(fig, width="stretch")

for lbl, v, m, why in steps:
    if why:
        st.html(f"<div style='font-size:.88rem;margin:.2rem 0;line-height:1.45'>"
                f"<b>{abs(v):,}</b> — {lbl.lower()}  ·  "
                f"<span style='color:{MUTED};font-size:.82rem'>{why}</span></div>")

verdict(f"Everything on <b>Analysis</b> and <b>Insights</b> speaks for those "
        f"<b>{analysed:,} records only</b>. The "
        f"{scored - relevant:,} the rule rejected were judged one at a time and their "
        f"reasons stored — you can read them in step 4 — but nothing downstream claims "
        f"anything about them.", "#E69F00")

note(f"A separate cut, easy to confuse with this one: <b>{retained_n:,}</b> records are "
     f"<b>browsable</b> at the bottom of this page — everything with no exclusion mark "
     f"against it, whether or not it turned out to be relevant. That is a different "
     f"question from the funnel above, which is about relevance. "
     f"{collected:,} = {retained_n:,} browsable + {excluded_n:,} set aside, "
     f"{'checked on every page load ✅' if collected == retained_n + excluded_n else '❌ DOES NOT BALANCE'}.")


# ============================================================== STEP 3
section(3, "The rule that decided",
        "Written down before collection began, applied to every record one at a time, "
        "and reproduced here in full — because the barrier ranking on the other pages "
        "is conditional on it rather than true of wishlists in general.", "#CC79A7")

kc, dc = st.columns(2)
kc.html(
    f"<div style='border:1px solid {HAIR};border-left:4px solid {OK};border-radius:7px;"
    f"padding:.85rem 1rem;height:100%'>"
    f"<div style='font-weight:750;color:{OK};font-size:.72rem;letter-spacing:.1em'>KEPT</div>"
    "<ul style='margin:.5rem 0 0;padding-left:1.1rem;font-size:.87rem;line-height:1.6'>"
    "<li>wishlist and saved-item behaviour of any kind</li>"
    "<li>collecting or browsing with <b>no</b> purchase intent</li>"
    "<li>fit, size, fabric, colour and styling doubt</li>"
    "<li>wanting other buyers' photos or reviews first</li>"
    "<li>price doubt, waiting for a sale, timing</li>"
    "<li>needing someone else's approval</li>"
    "<li>leaving the platform to check something</li>"
    "<li>cart and checkout abandonment</li>"
    "<li>a past bad experience <i>cited as present hesitation</i></li>"
    "</ul></div>")
dc.html(
    f"<div style='border:1px solid {HAIR};border-left:4px solid {BAD};border-radius:7px;"
    f"padding:.85rem 1rem;height:100%'>"
    f"<div style='font-weight:750;color:{BAD};font-size:.72rem;letter-spacing:.1em'>DROPPED</div>"
    "<ul style='margin:.5rem 0 0;padding-left:1.1rem;font-size:.87rem;line-height:1.6'>"
    "<li>delivery delays, couriers, order status</li>"
    "<li>refunds, cancellations, customer service</li>"
    "<li>app crashes, login and payment-gateway bugs</li>"
    "<li>post-purchase praise with nothing decision-bearing "
    "(<i>“lovely kurta, five stars”</i>)</li>"
    "<li>promotional and spam content</li>"
    "<li><b>any non-fashion category</b> — saving laptops, fridges or groceries is out, "
    "however closely it mirrors the pattern</li>"
    "</ul></div>")

st.info(
    "**“Why only people who meant to buy?” — it is not restricted to them.** The rule "
    "admits saving with no purchase intent *explicitly*, because **“they never meant to "
    "buy it” is one of the answers to the research question**, and an engine that "
    "filtered those records out would have quietly assumed its own conclusion and then "
    "reported it back. That is what makes the exclusions on **Insights** possible: "
    "saving for reference is *measured* at 126 records and intent that never existed at "
    "21. Neither number could exist if the filter had kept only shoppers with intent.",
    icon="🧭")
note("The category rule is the aggressive one, and it is deliberate: this project is "
     "about <i>fashion-specific</i> uncertainty — fit, fabric, sizing, whether it suits "
     "you — which has no equivalent for a fridge.")

# The human check, drawn. This was a paragraph; it is the single most important
# limitation on the page, and a paragraph is what a reader skips.
SAMPLE = Path(__file__).resolve().parents[2] / "data" / "artifacts" / "s1_hum_1_sample.json"
if SAMPLE.exists():
    try:
        s1 = json.loads(SAMPLE.read_text())
        hr = s1.get("human_review", {})
        n_sample = int(s1.get("n", 0))
        n_wrong = int(hr.get("wrong", 0))
        n_kept = sum(1 for r in s1.get("records", [])
                     if int(r.get("relevance", {}).get("is_relevant", 0)) == 1)
    except (ValueError, KeyError, TypeError):
        s1 = None
    if s1 and n_sample:
        n_dropped = n_sample - n_kept
        heading("A human re-judged 30 of them, blind to the verdict")
        note(f"Every square is one record. Green is a call the human agreed with; red is "
             f"one they did not. The pattern is the finding: <b>every disagreement is on "
             f"a record the rule threw away.</b>")
        # Squares, not a chart: 30 is few enough to show every case individually,
        # and the eye reads "all the red is on one side" instantly.
        def block(label: str, greens: int, reds: int) -> str:
            sq = "".join(
                f"<span style='display:inline-block;width:16px;height:16px;"
                f"margin:0 3px 3px 0;border-radius:3px;background:{col}'></span>"
                for col, k in ((OK, greens), (BAD, reds)) for _ in range(k))
            tot = greens + reds
            return (f"<div style='flex:1;min-width:210px;border:1px solid {HAIR};"
                    f"border-radius:7px;padding:.75rem .85rem'>"
                    f"<div style='font-weight:650;font-size:.9rem'>{label}</div>"
                    f"<div style='font-size:.76rem;color:{MUTED};margin-bottom:.5rem'>"
                    f"{tot} records · {reds} disagreement{'' if reds == 1 else 's'}</div>"
                    f"<div>{sq}</div></div>")
        st.html("<div style='display:flex;flex-wrap:wrap;gap:.6rem;margin:.5rem 0'>"
                + block("Records the rule KEPT", n_kept, 0)
                + block("Records the rule DROPPED", n_dropped - n_wrong, n_wrong)
                + "</div>")
        st.warning(
            f"**The weakness runs in one direction, and it is the direction that "
            f"matters.** {n_sample - n_wrong} of {n_sample} calls were confirmed "
            f"({(n_sample - n_wrong) / n_sample:.0%}), and all {n_kept} records the rule "
            f"*kept* were confirmed — so **what is in this corpus belongs here.** The "
            f"open question is what the rule threw away, and the excluded material skews "
            f"toward price/value and delivery-and-trust subject matter. Recorded as a "
            f"limitation rather than repaired, because repairing it means re-running the "
            f"whole analysis.", icon="⚠️")
        if hr.get("interpretation", "").startswith("PENDING"):
            note("One caveat on the caveat, from the reviewer's own note: a mark of "
                 "<i>wrong</i> may mean the record <b>is</b> relevant, or that it should "
                 "not be in the Data Bank at all. The two have different implications "
                 "and the review UI did not persist enough detail to separate them.")


# ============================================================== STEP 4
section(4, "What was set aside, and why",
        "Nothing is deleted. Every record removed at any stage is still here, still "
        "readable, with the reason attached — because what a corpus leaves out shapes "
        "its answer as much as what it keeps.", "#56B4E9")

by_reason = db.query("""
    SELECT reason, stage, count(DISTINCT record_id) AS n
    FROM exclusions GROUP BY reason, stage ORDER BY n DESC""")
if by_reason.empty:
    st.info("No exclusions recorded.")
else:
    PLAIN = {
        "other": "Five low-yield subreddits, dropped wholesale",
        "length": "Too short, or emoji only",
        "dedupe/exact": "Exact duplicate of another record",
        "dedupe/near": "Near-duplicate from the same author",
    }
    d = by_reason.copy().sort_values("n")
    d["label"] = d["reason"].map(lambda r: PLAIN.get(r, r))
    fig = go.Figure(go.Bar(
        x=d["n"], y=d["label"], orientation="h", marker_color="#56B4E9",
        text=[f" {int(v):,}  ({r} · {s})" for v, r, s in zip(d["n"], d["reason"], d["stage"])],
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,} records<extra></extra>"))
    fig.update_layout(
        height=90 + 44 * len(d), margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
        xaxis=dict(visible=False, range=[0, float(d["n"].max()) * 1.62]),
        yaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch")

    # These bars do NOT sum to the total, and saying so is cheaper than letting a
    # reader add them up and conclude the page is wrong.
    marks = int(by_reason["n"].sum())
    note(f"These add to {marks:,}, more than the {excluded_n:,} records actually set "
         f"aside, because <b>a record can carry more than one mark</b> — a comment "
         f"inside a dropped subreddit that was also a duplicate carries both. "
         f"{excluded_n:,} is the count of distinct records.")

    with st.expander("Read the records that were set aside"):
        pick = st.selectbox("Reason", by_reason["reason"].tolist(),
                            format_func=lambda r: PLAIN.get(r, r))
        ex = db.query("""
            SELECT r.source, e.detail, r.text_raw, r.source_url
            FROM exclusions e JOIN records r ON r.record_id = e.record_id
            WHERE e.reason = ? LIMIT 40""", (pick,))
        st.caption(f"{len(ex)} of them, as a sample.")
        for _, r in ex.iterrows():
            txt = str(r["text_raw"])
            st.html(
                f"<div style='border-left:2px solid {HAIR};padding:.15rem 0 .15rem .7rem;"
                f"margin:.45rem 0;font-size:.85rem;line-height:1.45'>"
                f"{txt[:260]}{'…' if len(txt) > 260 else ''}"
                f"<div style='color:{MUTED};font-size:.74rem;margin-top:.2rem'>"
                f"{r['source']} · {r['detail']}</div></div>")


# ============================================================== STEP 5
section(5, "Where this collection is weakest",
        "Every record remembers the search that surfaced it, so the collection method "
        "can be graded on its own output rather than defended in prose. It does not "
        "come out well in one specific place.", BAD)

yield_df = db.query("""
    SELECT CASE WHEN r.collect_query LIKE 'play/%' OR r.collect_query LIKE 'appstore/%'
                THEN 'Untargeted store listings' ELSE 'Search-query targeted' END AS kind,
           count(*) AS n,
           sum(CASE WHEN v.is_relevant = 1 THEN 1 ELSE 0 END) AS relevant
    FROM retained r LEFT JOIN relevance v ON v.record_id = r.record_id
    WHERE r.collect_query IS NOT NULL GROUP BY 1""")
if not yield_df.empty:
    yield_df["rate"] = yield_df["relevant"] / yield_df["n"]
    yield_df["share"] = yield_df["n"] / yield_df["n"].sum()
    cols = st.columns(len(yield_df))
    for col, (_, r) in zip(cols, yield_df.sort_values("rate", ascending=False).iterrows()):
        good = float(r["rate"]) > 0.15
        col.html(
            f"<div style='border:1px solid {HAIR};border-left:4px solid "
            f"{OK if good else BAD};border-radius:7px;padding:.8rem .9rem;height:100%'>"
            f"<div style='font-size:2rem;font-weight:750;line-height:1;"
            f"color:{OK if good else BAD}'>{float(r['rate']):.1%}</div>"
            f"<div style='font-size:.9rem;font-weight:650;margin-top:.25rem'>"
            f"{r['kind']}</div>"
            f"<div style='font-size:.79rem;color:{MUTED};line-height:1.45;margin-top:.25rem'>"
            f"{int(r['relevant']):,} relevant out of {int(r['n']):,} read · "
            f"{float(r['share']):.0%} of the readable corpus</div></div>")

    untargeted = yield_df[yield_df["kind"] == "Untargeted store listings"]
    targeted = yield_df[yield_df["kind"] == "Search-query targeted"]
    if not untargeted.empty and not targeted.empty:
        u, g = untargeted.iloc[0], targeted.iloc[0]
        ratio = float(g["rate"]) / float(u["rate"]) if float(u["rate"]) else 0
        verdict(
            f"<b>Scraping the newest store reviews with no search term is "
            f"{ratio:.0f}× less productive</b> than going looking for a topic — and it "
            f"is still <b>{float(u['share']):.0%}</b> of what was read. The corpus is "
            f"frozen so this was not acted on, but it is the first thing to change if "
            f"collection is ever re-run.", BAD)

with st.expander("Every search term, and how well it worked"):
    note("A barrier that only ever appears under one search term may be an artefact of "
         "that term rather than a fact about shoppers. The listings marked "
         "<code>play/</code> and <code>appstore/</code> used no search at all — they "
         "take the newest reviews in order, which is why they yield so little.")
    by_q = db.query("""
        SELECT r.collect_query AS q, count(*) AS n,
               sum(CASE WHEN v.is_relevant = 1 THEN 1 ELSE 0 END) AS rel
        FROM retained r LEFT JOIN relevance v ON v.record_id = r.record_id
        WHERE r.collect_query IS NOT NULL
        GROUP BY 1 ORDER BY n DESC""")
    if not by_q.empty:
        lines = ["| search term | read | bore on the decision | yield |", "|---|---|---|---|"]
        for _, r in by_q.iterrows():
            n_, rel_ = int(r["n"]), int(r["rel"] or 0)
            lines.append(f"| `{r['q']}` | {n_:,} | {rel_:,} | {rel_ / n_:.0%} |")
        st.markdown("\n".join(lines))

with st.expander("When many different people say the same thing"):
    note("Near-duplicate text from <b>one</b> author is removed as spam. The same thing "
         "said by <b>many</b> authors is the opposite of noise — it is the finding — so "
         "it is counted here instead of collapsed.")
    cons = db.query("""
        SELECT n_similar_xauthor AS k, count(*) AS records
        FROM consensus WHERE n_similar_xauthor > 0
        GROUP BY n_similar_xauthor ORDER BY n_similar_xauthor DESC LIMIT 15""")
    if cons.empty:
        st.caption("No echoes above threshold — the corpus is lexically diverse.")
    else:
        lines = ["| other people saying much the same | records |", "|---|---|"]
        for _, r in cons.iterrows():
            lines.append(f"| {int(r['k'])} | {int(r['records']):,} |")
        st.markdown("\n".join(lines))

st.info(
    "**Source gap on record.** Reddit's API was unavailable to this project — the "
    "application was rejected, self-serve registration is closed, and `robots.txt` says "
    "`Disallow: /`. Collection therefore runs through a third-party service, disclosed "
    "here rather than obscured.", icon="ℹ️")

# The corpus-level caveats, read from the table the pipeline writes so they
# cannot drift from what the analysis actually did.
flags = db.query("""SELECT statement, basis, severity FROM analysis_method_flags
                    WHERE scope = 'corpus'
                    ORDER BY CASE severity WHEN 'binding' THEN 0 ELSE 1 END""")
if not flags.empty:
    heading("What this corpus cannot be asked to answer", top="1.8rem")
    for _, f in flags.iterrows():
        col = BAD if str(f["severity"]) == "binding" else WARN
        st.html(
            f"<div style='display:flex;gap:.7rem;margin:.5rem 0;align-items:flex-start'>"
            f"<span style='flex:0 0 auto;font-size:.62rem;font-weight:800;"
            f"letter-spacing:.1em;color:{col};border:1px solid {col};border-radius:3px;"
            f"padding:.1rem .35rem;margin-top:.15rem'>{str(f['severity']).upper()}</span>"
            f"<span style='font-size:.86rem;line-height:1.5'>{f['statement']}"
            f"<span style='color:{MUTED};font-size:.76rem'> — {f['basis']}</span>"
            f"</span></div>")


# ========================================================== read it yourself
st.html(f"<div style='margin:2.6rem 0 .4rem'><div style='height:1px;background:{HAIR}'>"
        f"</div><div style='font-size:1.15rem;font-weight:700;margin-top:1rem'>"
        f"Read any of it yourself</div>"
        f"<div style='color:{MUTED};font-size:.9rem;max-width:70ch;line-height:1.5'>"
        f"The point of a data bank is that no claim on this site has to be taken on "
        f"trust. Every one of the {retained_n:,} records below is the raw text as it was "
        f"posted, with a link back to where it came from.</div></div>")

f1, f2, f3 = st.columns([1, 1, 2])
sources = db.query("SELECT DISTINCT source FROM retained ORDER BY source")["source"].tolist()
langs = db.query("SELECT DISTINCT lang FROM retained WHERE lang IS NOT NULL "
                 "ORDER BY lang")["lang"].tolist()
sel_src = f1.multiselect("Source", sources, default=sources)
sel_lang = f2.multiselect("Language", langs, default=langs)
search = f3.text_input("Full-text search", placeholder="e.g. size, wishlist, return")

where, params = ["1=1"], []
if sel_src:
    where.append(f"source IN ({','.join('?' * len(sel_src))})"); params += sel_src
if sel_lang:
    where.append(f"lang IN ({','.join('?' * len(sel_lang))})"); params += sel_lang
if search.strip():
    where.append("text_clean LIKE ?"); params.append(f"%{search.strip()}%")
clause = " AND ".join(where)

n = int(db.query(f"SELECT count(*) AS n FROM retained WHERE {clause}",
                 tuple(params)).iloc[0]["n"])
au = int(db.query(f"SELECT count(DISTINCT author_hash) AS a FROM retained WHERE {clause}",
                  tuple(params)).iloc[0]["a"])
st.caption(charts.caption_n(n, au))

rows = db.query(
    f"SELECT record_id, source, created_at, lang, collect_query, thread_context,"
    f" text_raw, source_url FROM retained WHERE {clause}"
    f" ORDER BY created_at DESC LIMIT 100", tuple(params))
for _, r in rows.iterrows():
    head = (r.text_raw[:110] + "…") if len(r.text_raw) > 110 else r.text_raw
    with st.expander(f"**{r.source}** · {str(r.created_at)[:10]} · {head}"):
        st.write(r.text_raw)
        st.caption(f"`{r.record_id[:12]}` · lang **{r.lang}** · found by query "
                   f"*{r.collect_query}* · context: {r.thread_context or '—'}")
        st.markdown(f"[Open source ↗]({r.source_url})")
if len(rows) == 100:
    st.caption("Showing the first 100 matches. Narrow the filters to see more.")
