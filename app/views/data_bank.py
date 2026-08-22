"""Data Bank — the provenance layer (FR-1.5, FR-1.6, NFR-1, AC-2).

Every downstream claim must be clickable back to its raw evidence. This
page is what makes that true: browse, filter, search, and see exactly what
was collected AND what was excluded, with the reason.

The composition dashboard is not decoration. It is the evidence base for
the source-bias caveats in problemstatement.md §8 — a mentor asking
"what's in your corpus?" gets an answer with numbers.
"""

import streamlit as st

from lib import charts, db, story as S

st.title("The evidence")
st.caption("Every comment, post and review this project read — and everything it threw "
           "away, with the reason.")

status, detail = db.db_status()
if status != "ok":
    # Report which condition actually holds. "Not collected yet" asserted a
    # cause the check never established, and read as a project that never ran.
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

# ---------------------------------------------------------------- overview
totals = db.query("""
    SELECT (SELECT count(*) FROM records)                                   AS collected,
           (SELECT count(*) FROM retained)                                  AS retained,
           (SELECT count(DISTINCT record_id) FROM exclusions)               AS excluded,
           (SELECT count(DISTINCT author_hash) FROM retained
             WHERE author_hash IS NOT NULL)                                 AS authors
""").iloc[0]

c1, c2, c3 = st.columns(3)
c1.metric("Collected", f"{int(totals.collected):,}")
c2.metric("Kept", f"{int(totals.retained):,}")
c3.metric("Set aside", f"{int(totals.excluded):,}")

ok = int(totals.collected) == int(totals.retained) + int(totals.excluded)
st.caption(
    f"{'✅' if ok else '❌'} {int(totals.collected):,} collected "
    f"= {int(totals.retained):,} kept + {int(totals.excluded):,} set aside. "
    "**The sum is checked on every page load** — it is what guarantees no record "
    "disappeared without a logged reason. Set-aside records are not deleted; they are "
    "browsable in the last tab with the reason attached."
)
st.caption(f"Written by **{int(totals.authors):,} different people**. "
           + S.explain("authors"))

# ------------------------------------------------------------------ funnel
# Moved here from Home: the cuts are a fact about the corpus, and this is the
# page that owns the corpus. Home now only points at it.
st.divider()
st.subheader("From 12,002 records to the ones the analysis runs on")
st.caption(
    "Public conversation is the only data this project has — there is no access to "
    "Myntra's analytics — so the first question is not *what does it say* but *how much "
    "of it is about saving and buying at all.* Each cut below is a stated rule, applied "
    "in order.")

funnel = db.query("""
    SELECT (SELECT count(*) FROM records)                                AS collected,
           (SELECT count(*) FROM relevance)                              AS scored,
           (SELECT count(*) FROM relevance WHERE is_relevant = 1)        AS relevant,
           (SELECT count(DISTINCT c.record_id) FROM classifications c
             WHERE c.record_id NOT IN (SELECT record_id FROM exclusions)) AS analysed
""").iloc[0]

cuts = [("Collected from four public sources", int(funnel.collected),
         "YouTube comments, Reddit threads, Play Store and App Store reviews"),
        ("Survived cleaning and de-duplication", int(funnel.scored),
         "boilerplate, duplicates and empty text removed"),
        ("Bear on saving or buying a fashion item", int(funnel.relevant),
         "wishlist behaviour of ANY kind, including saving with no intention of buying"),
        ("Analysed", int(funnel.analysed),
         "after dropping five subreddits that produced almost no relevant records")]
st.plotly_chart(
    charts.attrition([t for t, _, _ in cuts], [n for _, n, _ in cuts],
                     title="Records surviving each cut"),
    width="stretch")
for t, n, why in cuts:
    st.html(f"<div style='font-size:.95rem;margin:.15rem 0'><b>{n:,}</b> — {t}  ·  "
            f"<span style='color:#8a8a8a;font-size:.85rem'>{why}</span></div>")

st.info(
    f"**Only the last bar is classified.** The **{int(funnel.analysed):,}** analysed "
    f"records are the only ones that carry a journey step and a barrier. The "
    f"**{int(funnel.scored) - int(funnel.relevant):,}** records the relevance rule "
    "rejected were judged one by one and their reason stored — browse them in the last "
    "tab — but nothing on **Analysis** or **Insights** speaks for them.", icon="🎯")

# "Why only people who meant to buy?" is the first question a reader asks of a
# filter this narrow, and the answer is that it is not that narrow: the rule
# admits saving with no purchase intent on purpose, because a wishlist that was
# never a shopping list is one of the ANSWERS, not a record to discard.
with st.expander("“Why only people who meant to buy?” — the relevance rule, in full"):
    st.markdown(
        "**It is not restricted to people who meant to buy.** The rule admits **wishlist "
        "and saved-item behaviour of any kind**, and says so explicitly, including "
        "*collecting or browsing with no purchase intent at all*. Saving for inspiration, "
        "saving as a taste archive, saving something you never intended to buy — all "
        "kept, because **“they never meant to buy it” is one of the answers to the "
        "research question**, and an engine that filtered those records out would have "
        "quietly assumed its own conclusion and then reported it back.\n\n"
        "That is what makes the exclusions on **Insights** possible: saving for reference "
        "is *measured* at 126 records and intent that never existed at 21 — roughly one "
        "saved item in eight is not a conversion problem at all. Neither number could "
        "exist if the filter had kept only shoppers with intent.")
    kc, dc = st.columns(2)
    kc.markdown(
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
    dc.markdown(
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
        "— which has no equivalent for a fridge. It is also why the ranking is "
        "conditional on this rule rather than true of wishlists in general.")
    st.warning(
        "**The rule's known weakness runs in exactly that direction.** A human reviewer "
        "re-judged 30 randomly drawn records and disagreed on 11 — and **every one was a "
        "record the filter had rejected.** All 9 it accepted were confirmed. So what is in "
        "this corpus belongs here, and the open question is what the rule threw away. "
        "Recorded as a limitation rather than repaired, because repairing it means "
        "re-running the analysis.", icon="⚠️")

st.divider()

tab_browse, tab_comp, tab_excl = st.tabs(
    ["Read the records", "What is in the corpus", "What was set aside"])

# ---------------------------------------------------------------- browse
with tab_browse:
    f1, f2, f3 = st.columns([1, 1, 2])
    sources = db.query("SELECT DISTINCT source FROM retained ORDER BY source")["source"].tolist()
    langs = db.query("SELECT DISTINCT lang FROM retained WHERE lang IS NOT NULL ORDER BY lang")["lang"].tolist()
    sel_src = f1.multiselect("Source", sources, default=sources)
    sel_lang = f2.multiselect("Language", langs, default=langs)
    search = f3.text_input("Full-text search", placeholder="e.g. size, wishlist, return")

    where = ["1=1"]
    params: list = []
    if sel_src:
        where.append(f"source IN ({','.join('?' * len(sel_src))})"); params += sel_src
    if sel_lang:
        where.append(f"lang IN ({','.join('?' * len(sel_lang))})"); params += sel_lang
    if search.strip():
        where.append("text_clean LIKE ?"); params.append(f"%{search.strip()}%")

    clause = " AND ".join(where)
    n = int(db.query(f"SELECT count(*) AS n FROM retained WHERE {clause}", tuple(params)).iloc[0]["n"])
    a = int(db.query(f"SELECT count(DISTINCT author_hash) AS a FROM retained WHERE {clause}",
                     tuple(params)).iloc[0]["a"])
    st.caption(charts.caption_n(n, a))

    rows = db.query(
        f"SELECT record_id, source, created_at, lang, collect_query, thread_context,"
        f" text_raw, source_url FROM retained WHERE {clause}"
        f" ORDER BY created_at DESC LIMIT 100", tuple(params))

    for _, r in rows.iterrows():
        head = (r.text_raw[:110] + "…") if len(r.text_raw) > 110 else r.text_raw
        with st.expander(f"**{r.source}** · {str(r.created_at)[:10]} · {head}"):
            st.write(r.text_raw)
            st.caption(
                f"`{r.record_id[:12]}` · lang **{r.lang}** · "
                f"found by query *{r.collect_query}* · context: {r.thread_context or '—'}"
            )
            st.markdown(f"[Open source ↗]({r.source_url})")
    if len(rows) == 100:
        st.caption("Showing the first 100 matches. Narrow the filters to see more.")

# ---------------------------------------------------------- composition
with tab_comp:
    st.subheader("Where it all came from")
    st.caption(
        "**Read this as a map of where people talk, not of who shops.** YouTube leads "
        "because YouTube comment threads are long and public, not because YouTube users "
        "hesitate more. Every claim on the Analysis page that leans on one source alone "
        "is flagged there for exactly this reason."
    )

    by_src = db.query("""
        SELECT source, count(*) AS n, count(DISTINCT author_hash) AS authors
        FROM retained GROUP BY source ORDER BY n DESC""")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(charts.bar(by_src, "source", "n", title="Records per source", n_col="n"),
                        width='stretch')
    with right:
        by_lang = db.query("""
            SELECT lang, count(*) AS n FROM retained
            WHERE lang IS NOT NULL GROUP BY lang ORDER BY n DESC""")
        st.plotly_chart(charts.bar(by_lang, "lang", "n", title="Language mix", n_col="n"),
                        width='stretch')

    st.markdown("**Per-source detail**")
    st.dataframe(by_src, width='stretch', hide_index=True)

    st.markdown("---")
    with st.expander("Which searches found this material, and how well they worked"):
        st.caption(
            "Each record remembers the search that surfaced it, so a barrier's size can be "
            "checked against the words used to go looking for it. A barrier that only ever "
            "appears under one search term may be an artefact of that term. **The store "
            "listings marked `play/` and `appstore/` used no search at all** — they take "
            "the newest reviews, which is why they yield so little."
        )
        by_q = db.query("""
            SELECT collect_query AS search, count(*) AS found,
                   sum(CASE WHEN v.is_relevant = 1 THEN 1 ELSE 0 END) AS "bore on the decision"
            FROM retained r LEFT JOIN relevance v ON v.record_id = r.record_id
            WHERE collect_query IS NOT NULL
            GROUP BY collect_query ORDER BY found DESC""")
        st.dataframe(by_q, width='stretch', hide_index=True)

    with st.expander("When many different people say the same thing"):
        st.caption(
            "Near-duplicate text from **one** author is removed as spam. The same thing said "
            "by **many** authors is the opposite of noise — it is the finding — so it is "
            "counted here instead of collapsed."
        )
        cons = db.query("""
            SELECT n_similar_xauthor AS "other people saying much the same",
                   count(*) AS records
            FROM consensus WHERE n_similar_xauthor > 0
            GROUP BY n_similar_xauthor ORDER BY n_similar_xauthor DESC LIMIT 15""")
        if cons.empty:
            st.caption("No echoes above threshold — the corpus is lexically diverse.")
        else:
            st.dataframe(cons, width='stretch', hide_index=True)

    st.info(
        "**Source gap on record.** Reddit's API was unavailable to this project "
        "(application rejected; self-serve registration closed; robots.txt `Disallow: /`). "
        "Collection therefore runs through a third-party service, disclosed here rather "
        "than obscured. Play and App Store are correlated sources, so effective source "
        "independence is lower than the source count suggests — triangulation claims are "
        "weighted accordingly.",
        icon="ℹ️",
    )

# ------------------------------------------------------------ exclusions
with tab_excl:
    st.subheader("What was set aside, and why")
    st.caption("Nothing is deleted. Every record below is still here, still readable, with "
               "the reason it was put aside — because what a corpus leaves out shapes its "
               "answer as much as what it keeps.")

    by_reason = db.query("""
        SELECT reason, stage, count(DISTINCT record_id) AS n
        FROM exclusions GROUP BY reason, stage ORDER BY n DESC""")
    st.plotly_chart(charts.bar(by_reason, "reason", "n", title="Exclusions by reason", n_col="n"),
                    width='stretch')
    st.dataframe(by_reason, width='stretch', hide_index=True)

    reasons = by_reason["reason"].tolist()
    if reasons:
        pick = st.selectbox("Inspect excluded records", reasons)
        ex = db.query("""
            SELECT r.record_id, r.source, e.detail, r.text_raw, r.source_url
            FROM exclusions e JOIN records r ON r.record_id = e.record_id
            WHERE e.reason = ? LIMIT 50""", (pick,))
        st.caption(f"{len(ex)} shown")
        st.dataframe(ex, width='stretch', hide_index=True)
