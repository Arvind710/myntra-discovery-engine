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
