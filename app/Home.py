"""Home — what this is and how it works. This page IS the one-slide (AC-8)."""

import json
from pathlib import Path

import streamlit as st

from lib import db, framework as F

ROOT = Path(__file__).resolve().parents[1]
st.set_page_config(page_title="Myntra Discovery Engine", page_icon="🔎", layout="wide")

st.title("AI Discovery Engine — Myntra wishlist conversion")
st.caption("Turning public user feedback into a quantified, source-cited ranking of the "
           "barriers preventing wishlist → purchase conversion.")

pop = db.corpus_is_populated()
if pop:
    m = db.query("""SELECT (SELECT count(*) FROM records)                        AS collected,
                           (SELECT count(*) FROM relevance WHERE is_relevant=1)  AS relevant,
                           (SELECT count(DISTINCT author_hash) FROM records
                             WHERE author_hash IS NOT NULL)                      AS authors,
                           (SELECT count(*) FROM record_meta)                    AS classified""").iloc[0]
    a, b, c, d = st.columns(4)
    a.metric("Records collected", f"{int(m.collected):,}")
    b.metric("Relevant to the decision", f"{int(m.relevant):,}")
    c.metric("Distinct authors", f"{int(m.authors):,}")
    d.metric("Classified", f"{int(m.classified):,}")

left, right = st.columns([3, 2])

with left:
    st.subheader("The question")
    st.markdown(
        "> Which barrier stops users buying what they already saved — and how "
        "confident can we be, given that public feedback measures **who talks about "
        "what**, not drop-off rates?"
    )

    st.subheader("How it works")
    st.markdown("""
**1 · Collect.** Reddit, YouTube, Play Store, App Store, Myntra product reviews, and
verified published research. Every record keeps its permalink, a pseudonymised author
id, and the search query that surfaced it — so a theme's prevalence can be audited
against the terms used to find it.

**2 · Filter.** A written rubric separates feedback bearing on the *save → purchase*
decision from general complaints. The hardest boundary is deliberate: a past bad
experience cited as a reason for **present** hesitation is in; a complaint about a late
order is out.

**3 · Classify.** Every relevant record is scored against a **pre-registered, frozen
codebook** — stage first, then codes within that stage. Pre-registering it before
scoring is what stops the analysis quietly confirming its author's expectations.

**4 · Quantify.** Prevalence with denominators, distinct-author counts, co-occurrence
lift, workaround intensity, and per-segment barrier profiles.
""")

    st.subheader("What makes a number here defensible")
    st.markdown("""
- **Every quote is verified as an exact substring** of the record it cites. A span that
  is not exact is not evidence and is never displayed.
- **Every count carries a distinct-author count.** 200 records from 12 people is a
  weaker claim than 200 from 180.
- **Nothing is deleted silently.** Every excluded record is logged with its reason and
  is browsable.
- **Measurements beat predictions, including our own.** The prefilter was removed after
  it was measured dropping 23% of relevant records; a model-tier decision was reversed
  after testing it on hand-labelled boundary cases.
""")

    st.info(
        "**Proxy discipline.** Every share reported here is a share of *discussion*, "
        "never a conversion or drop-off rate. Silent barriers — *'I forgot the wishlist "
        "existed'* — are under-represented by construction, because forgetting produces "
        "no complaint.", icon="⚠️")

with right:
    st.subheader("Status")
    frozen = ROOT / "codebook" / "FROZEN.json"
    if frozen.exists():
        fz = json.loads(frozen.read_text())
        st.metric("Codebook", fz["version_string"])
        st.caption(f"{fz['n_scored_codes']} codes · frozen {fz['frozen_at'][:10]}, "
                   "before any scoring")

    if pop:
        src = db.query("SELECT source, count(*) AS n FROM retained GROUP BY source ORDER BY n DESC")
        st.markdown("**Corpus by source**")
        st.dataframe(src, width="stretch", hide_index=True)

        seg = db.query("""SELECT segment_name, count(*) AS n FROM segments_v2
                          GROUP BY segment_id, segment_name ORDER BY n DESC""")
        if not seg.empty:
            st.markdown("**Segments** (derived, 100% coverage)")
            st.dataframe(seg, width="stretch", hide_index=True)

    st.markdown("""
| Phase | Ships | |
|---|---|---|
| P0 | Foundation & freeze | ✅ |
| P1 | Data Bank | ✅ |
| P2 | Analysis | ✅ |
| P3 | Insights | ⬜ |
| P4 | Ask | ⬜ |
""")

st.divider()
st.caption("Public data only · authors pseudonymised · no PII in outputs. "
           "A research instrument, not a Myntra product.")
