"""Data Bank — the provenance layer (FR-1.5, FR-1.6, NFR-1, AC-2).

Every downstream claim must be clickable back to its raw evidence. This
page is what makes that true: browse, filter, search, and see exactly what
was collected AND what was excluded, with the reason.

The composition dashboard is not decoration. It is the evidence base for
the source-bias caveats in problemstatement.md §8 — a mentor asking
"what's in your corpus?" gets an answer with numbers.
"""

import streamlit as st

from lib import charts, db

st.set_page_config(page_title="Data Bank", page_icon="🗂️", layout="wide")
st.title("Data Bank")
st.caption("Every record, its provenance, and everything that was excluded — with the reason.")

if not db.corpus_is_populated():
    st.info("The corpus has not been collected yet. Run the collectors in `pipeline/collect/`.")
    st.stop()

# ---------------------------------------------------------------- overview
totals = db.query("""
    SELECT (SELECT count(*) FROM records)                                   AS collected,
           (SELECT count(*) FROM retained)                                  AS retained,
           (SELECT count(DISTINCT record_id) FROM exclusions)               AS excluded,
           (SELECT count(DISTINCT author_hash) FROM retained
             WHERE author_hash IS NOT NULL)                                 AS authors
""").iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Collected", f"{int(totals.collected):,}")
c2.metric("Retained", f"{int(totals.retained):,}")
c3.metric("Excluded", f"{int(totals.excluded):,}",
          help="Nothing is dropped silently — every exclusion is logged with a reason (FR-1.6)")
c4.metric("Distinct authors", f"{int(totals.authors):,}",
          help="EC-COL-9: 200 records from 12 authors is a weaker claim than 200 from 180")

ok = int(totals.collected) == int(totals.retained) + int(totals.excluded)
st.caption(
    f"{'✅' if ok else '❌'} **S1-INV-1 accounting identity**: "
    f"{int(totals.collected):,} collected = {int(totals.retained):,} retained "
    f"+ {int(totals.excluded):,} excluded. No record vanishes unlogged."
)

tab_browse, tab_comp, tab_excl = st.tabs(["Browse", "Corpus composition", "Exclusion log"])

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
    st.subheader("What is actually in the corpus")
    st.caption(
        "Volume across sources reflects platform activity, not user population "
        "(problemstatement.md §8). These numbers are the evidence base for that caveat, "
        "not a measure of the funnel."
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

    st.markdown("**Yield per search query** — bias auditing (EC-COL-12)")
    st.caption(
        "Stored so a theme's prevalence can be audited against the search terms that found it. "
        "A code that only appears under one query may be an artefact of that query."
    )
    by_q = db.query("""
        SELECT collect_query AS query, count(*) AS n,
               count(DISTINCT author_hash) AS authors
        FROM retained WHERE collect_query IS NOT NULL
        GROUP BY collect_query ORDER BY n DESC""")
    st.dataframe(by_q, width='stretch', hide_index=True)

    st.markdown("**Cross-author consensus** — measured, never removed")
    st.caption(
        "EC-CLEAN-1: many different people saying the same thing IS the finding. "
        "Near-duplicate removal is scoped to a single author; cross-author similarity "
        "is recorded here as evidence strength instead."
    )
    cons = db.query("""
        SELECT n_similar_xauthor AS distinct_authors_echoing, count(*) AS records
        FROM consensus WHERE n_similar_xauthor > 0
        GROUP BY n_similar_xauthor ORDER BY n_similar_xauthor DESC LIMIT 15""")
    if cons.empty:
        st.caption("No cross-author echoes above threshold — the corpus is lexically diverse.")
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
    st.subheader("What was excluded, and why")
    st.caption("Corpus composition is itself a finding (FR-1.6). Nothing is dropped silently.")

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
