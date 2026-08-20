"""Home — what this is, in the order a stranger needs it (AC-8).

The old version opened with the pipeline: collect, filter, classify, quantify.
That is how the system works, not what it found, and it asks the reader to care
about the machinery before they have been given a reason to. This version leads
with the question, then the model that makes every later number legible, then
the answer — and puts the method behind a fold for the people who want it.
"""

import json
from pathlib import Path

import streamlit as st

from lib import db, framework as F, story as S

ROOT = Path(__file__).resolve().parents[1]

st.title("Why don't people buy what they saved?")
st.caption("A discovery engine that reads public conversation at scale and turns it "
           "into a ranked, source-cited account of what gets in the way.")

pop = db.corpus_is_populated()

# ------------------------------------------------------------- the model
st.markdown(S.THE_MODEL)

if pop:
    stage_n = {r["stage"]: int(r["n"]) for _, r in
               db.query("SELECT stage, sum(n) AS n FROM analysis_stage_outcome "
                        "GROUP BY stage").iterrows()}
    cols = st.columns(4)
    for i, (col, s) in enumerate(zip(cols, S.STAGE_ORDER), 1):
        spec = S.stages()[s]
        with col:
            st.markdown(
                f"<div style='border-top:4px solid {S.STAGE_COLOUR[s]};padding-top:.5rem'>"
                f"<span style='font-size:.72rem;letter-spacing:.08em;color:#888'>"
                f"STEP {i}</span><br><b>{spec['title']}</b></div>",
                unsafe_allow_html=True)
            st.caption(spec["question"])

    st.divider()

    # ------------------------------------------------------------ the answer
    st.subheader("What the corpus says")
    opp = db.query("""SELECT o.code, o.n, o.rank FROM analysis_opportunity o
                      WHERE o.rank IS NOT NULL ORDER BY o.rank LIMIT 3""")
    if not opp.empty:
        st.caption("The three barriers that rank highest once size, intensity, evidence "
                   "quality and *whether it can be fixed without a discount* are all "
                   "taken into account:")
        for _, r in opp.iterrows():
            st.markdown(f"**{int(r['rank'])}. “{S.voice(r['code'])}”**  ·  "
                        f"{int(r['n'])} records")
            st.caption(S.plain(r["code"]))
        st.caption("Full ranking, the weights behind it, and how much it moves when you "
                   "change them — on the **Insights** page.")

    st.divider()
    m = db.query("""SELECT (SELECT count(*) FROM records)                        AS collected,
                           (SELECT count(*) FROM relevance WHERE is_relevant=1)  AS relevant,
                           (SELECT count(DISTINCT author_hash) FROM records
                             WHERE author_hash IS NOT NULL)                      AS authors""").iloc[0]
    a, b, c = st.columns(3)
    a.metric("Comments, posts and reviews read", f"{int(m.collected):,}")
    b.metric("Bearing on the save-to-buy decision", f"{int(m.relevant):,}")
    c.metric("Different people", f"{int(m.authors):,}")
    st.caption("Everything downstream is counted over the middle number. The gap between "
               "the first two is the filter doing its job — most public conversation about "
               "a shopping app is about delivery and refunds, not about deciding.")

st.warning(S.PROXY_WARNING, icon="⚠️")

# ------------------------------------------------------------- the method
with st.expander("How it works, and why you should believe any of it"):
    st.markdown("""
**The barrier list was written down and frozen before a single record was read.** That is
the whole defence against finding what you expected to find: the engine cannot invent a
category mid-analysis to fit a result it likes. Where a record fits nothing on the list,
it goes to a residual bucket — and the size of that bucket is reported, because if it
were large the list would be wrong.

**Every quote is verified word-for-word** against the record it came from. A quote that is
not an exact substring is not evidence and is never shown.

**Every count carries how many *different people* it came from.** 200 records from 12
people is a much weaker claim than 200 from 180.

**Nothing is deleted quietly.** Every excluded record is logged with its reason and stays
browsable on the Data Bank page.

**Measurements beat predictions, including our own.** A pre-filter was removed after it was
measured throwing away 23% of relevant records to save $2.49. A model-tier decision was
reversed after testing it on hand-labelled boundary cases. Both are written up in the repo
with the numbers that overturned them.
""")

with st.expander("What this engine cannot tell you"):
    st.markdown("""
- **It is not a funnel.** No user-level data exists here. Nothing on any page is a drop-off
  or conversion rate, however much it may look like one.
- **Quiet barriers are under-counted by construction.** Forgetting a wishlist produces no
  complaint. The Insights page quantifies how far off that could throw the ranking.
- **The relevance rule is narrow on purpose**, and a human reviewer disagreed with it on 11
  of 30 randomly drawn records — every one of them a record the filter had *rejected*.
  Recorded as a limitation rather than repaired, because fixing it would mean re-running
  the analysis.
- **It is a research instrument, not a Myntra product**, built on public data only.
""")

with st.sidebar:
    frozen = ROOT / "codebook" / "FROZEN.json"
    if frozen.exists():
        fz = json.loads(frozen.read_text())
        st.caption(f"Barrier list **{fz['version_string']}**  \n{fz['n_scored_codes']} "
                   f"barriers, frozen {fz['frozen_at'][:10]} — before any scoring")
    if pop:
        st.caption("**Phases**  \nP0 foundation ✅  \nP1 data bank ✅  \nP2 analysis ✅  \n"
                   "P3 insights ✅  \nP4 ask ⬜")

st.divider()
st.caption("Public data only · authors pseudonymised · no personal information in outputs.")
