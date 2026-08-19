"""Home — what this is and how it works.

This page IS the one-slide (AC-8). It is written properly in P5, because
only then is it true. Until then it states the build status honestly rather
than describing capabilities that do not exist yet.
"""

import json
from pathlib import Path

import streamlit as st

from lib import db

ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="Myntra Discovery Engine", page_icon="🔎", layout="wide")

st.title("AI Discovery Engine — Myntra wishlist conversion")
st.caption(
    "Turning public user feedback into a quantified, source-cited ranking of the "
    "barriers preventing wishlist → purchase conversion."
)

st.warning(
    "**Build in progress.** Phase 0 (Foundation) is complete. The Data Bank, "
    "Analysis, Insights and Ask sections arrive with Phases 1–4. "
    "Nothing on this site reports a finding yet.",
    icon="🚧",
)

left, right = st.columns([3, 2])

with left:
    st.subheader("The question")
    st.markdown(
        "> Which barrier stops users from buying what they already saved — and "
        "how confident can we be, given that public feedback measures **who "
        "talks about what**, not drop-off rates?"
    )
    st.markdown(
        "The engine classifies every relevant record against a **pre-registered, "
        "closed codebook of 33 hypothesis codes** across four funnel stages. "
        "A fixed codebook is what gives prevalence a denominator and makes "
        "opportunities comparable — and pre-registering it before scoring is "
        "what stops the analysis quietly confirming its author's priors."
    )
    st.markdown(
        "**Proxy discipline.** Every share reported here is a share of "
        "*discussion*, never a conversion or drop-off rate. Silent barriers "
        "(*'I forgot the wishlist existed'*) are under-represented by "
        "construction, because forgetting produces no complaint."
    )

with right:
    st.subheader("Build status")
    frozen_path = ROOT / "codebook" / "FROZEN.json"
    if frozen_path.exists():
        frozen = json.loads(frozen_path.read_text())
        st.metric("Codebook", frozen["version_string"])
        st.caption(
            f"{frozen['n_scored_codes']} codes, frozen "
            f"{frozen['frozen_at'][:10]} — before any scoring (FR-5.6)"
        )
    st.metric("Corpus", "populated" if db.corpus_is_populated() else "not yet collected")
    run_id = db.published_run_id()
    st.metric("Published run", run_id or "none pinned")

    st.markdown(
        """
| Phase | Ships | Status |
|---|---|---|
| P0 | Foundation & freeze | ✅ |
| P1 | Data Bank | ⬜ |
| P2 | Analysis | ⬜ |
| P3 | Insights | ⬜ |
| P4 | Ask | ⬜ |
"""
    )

st.divider()
st.caption(
    "Public data only, authors pseudonymised, no PII in outputs (NFR-7). "
    "This is a research instrument, not a Myntra product."
)
