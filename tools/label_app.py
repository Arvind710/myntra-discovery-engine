"""Gold-set labelling — the human ground truth every P2 metric is scored against.

WHY THIS PAGE IS DELIBERATELY BLIND
-----------------------------------
It shows the record text and NOTHING the model produced: no assigned codes,
no confidence, no relevance verdict, no stage. Showing them would turn the
task from "what is this person saying?" into "do I agree with this
suggestion?", and anchoring is strong enough that agreement would rise
without accuracy rising. Every metric downstream — T-1 through T-4 — would
improve and the improvement would be an artefact. AC-9 rests on this page
being independent, so the blinding is load-bearing, not a nicety.

WHY IT LIVES OUTSIDE `app/` AND REFUSES TO RUN ON STREAMLIT CLOUD
-----------------------------------------------------------------
implementationplan.md 2.9 names this `app/pages/9_Label.py`, but §0.5 pins
the public nav to four sections and Streamlit auto-discovers everything in
`app/pages/`. Left there it would show an evaluator a fifth entry that only
errors. It is an operator tool, not a project section, so it runs as its own
local app: `streamlit run tools/label_app.py`.

Streamlit Community Cloud gives the container an ephemeral filesystem that
is rebuilt on every push and on idle restart. A write to corpus.db there
survives until the next rebuild and then disappears — with no error, and no
way to recover the hours spent. So this page runs LOCALLY, against the
working copy, and the labels are committed to git like any other artefact.
There is also a JSON export on every sitting, because three hours of human
judgement should never exist in exactly one place.

PROTOCOL (Appendix B / EC-VAL-1)
--------------------------------
Two sittings. Twenty sitting-1 records reappear in sitting 2 without being
marked as repeats — that is T-13, intra-rater agreement, and it only means
anything if the labeller cannot tell. Do not go looking for them.

Where the model looks right and the human looks wrong, the gold label MAY be
amended — but only with the reason written into `notes` (EC-VAL-5). Gold is
one person's judgement recorded honestly, not ground truth handed down.
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "corpus.db"

st.set_page_config(page_title="Gold labelling", page_icon="✍️", layout="wide")


# --------------------------------------------------------------------------
# Environment guard — before anything else, and before any keystroke is spent
# --------------------------------------------------------------------------
def _is_ephemeral_host() -> bool:
    """Streamlit Community Cloud mounts the repo at /mount/src. Anything under
    it is rebuilt on push. Checking the mount point is checking the property
    (this disk does not persist), not a proxy for it."""
    return str(ROOT).startswith("/mount/src")


if _is_ephemeral_host():
    st.error(
        "**This page cannot be used here.** Streamlit Cloud rebuilds this "
        "container's filesystem on every push and on idle restart, so labels "
        "written here would be lost silently — after the hours were spent, with "
        "no error shown.\n\n"
        "Run it locally instead, from the repo root:\n\n"
        "```\nstreamlit run tools/label_app.py\n```\n\n"
        "The labels land in `data/corpus.db` "
        "in your working copy and are committed like any other artefact.",
        icon="🛑")
    st.stop()


# --------------------------------------------------------------------------
# Password gate (EC-OPS-7)
# --------------------------------------------------------------------------
def _gate() -> bool:
    want = st.secrets.get("LABEL_PASSWORD")
    if not want:
        st.error("`LABEL_PASSWORD` is not set in `.streamlit/secrets.toml`.", icon="🔒")
        return False
    if st.session_state.get("label_ok"):
        return True
    with st.form("gate"):
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Unlock") and pw == want:
            st.session_state["label_ok"] = True
            st.rerun()
    return False


if not _gate():
    st.stop()


# --------------------------------------------------------------------------
# Data access — read/write, unlike the rest of the app
# --------------------------------------------------------------------------
@st.cache_resource
def rw() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


@st.cache_resource
def codebook() -> dict:
    return yaml.safe_load((ROOT / "codebook" / "codebook_v1.yaml").read_text())


con = rw()
CB = codebook()
CODES = [c for c in CB["codes"] if c["id"] != "Z-99"]
STAGE_NAMES = {"A": "A · Recall / Discovery", "B": "B · Wishlist / Navigation",
               "C": "C · Confidence & Decision", "D": "D · Checkout / Conversion"}
SEGMENTS = {
    1: "① Collectors — saving as browsing, no purchase intent",
    2: "② Lapsed Intenders — intent existed, has since died",
    3: "③ Ready Buyers — intent live, no unresolved doubt",
    4: "④ Stuck Deciders — intent live, doubt voiced and unresolved",
    5: "⑤ Committed Waiters — waiting on a named external condition",
    6: "⑥ Hesitant Waiters — waiting, condition vague or self-imposed",
}

st.title("✍️ Gold-set labelling")
st.caption("Independent human labels. Everything you write here is what the "
           "classifier is graded against — AC-9, T-1 through T-4, T-13.")

if con.execute("SELECT count(*) FROM gold_sample").fetchone()[0] == 0:
    st.error("No sampling frame. Run `python pipeline/validate/goldset.py` first.",
             icon="⚠️")
    st.stop()


# --------------------------------------------------------------------------
# Sitting selection and progress
# --------------------------------------------------------------------------
def counts(sitting: str) -> tuple[int, int]:
    total = con.execute("SELECT count(*) FROM gold_sample WHERE sitting_id=?",
                        (sitting,)).fetchone()[0]
    done = con.execute(
        "SELECT count(*) FROM gold_sample s JOIN gold g"
        " ON g.record_id=s.record_id AND g.pass_no=s.pass_no"
        " WHERE s.sitting_id=?", (sitting,)).fetchone()[0]
    return done, total


with st.sidebar:
    st.subheader("Sitting")
    sitting = st.radio("Sitting", ["sitting-1", "sitting-2"], label_visibility="collapsed")
    d1, t1 = counts("sitting-1")
    d2, t2 = counts("sitting-2")
    st.progress(d1 / max(t1, 1), text=f"sitting-1 · {d1}/{t1}")
    st.progress(d2 / max(t2, 1), text=f"sitting-2 · {d2}/{t2}")
    if sitting == "sitting-2" and d1 < t1:
        st.warning(f"Sitting 1 has {t1 - d1} left. The two-sitting split exists so "
                   "intra-rater drift is measurable — finish sitting 1 first.", icon="⏳")
    st.divider()
    # Insurance. Three hours of judgement should not live in one sqlite file.
    rows = [dict(r) for r in con.execute("SELECT * FROM gold ORDER BY labelled_at")]
    st.download_button(
        f"⬇ Export {len(rows)} labels (JSON)",
        json.dumps(rows, indent=2), file_name="gold_backup.json",
        mime="application/json", disabled=not rows, width="stretch")

done, total = counts(sitting)
st.progress(done / max(total, 1), text=f"{done} of {total} labelled in {sitting}")

nxt = con.execute(
    """SELECT s.record_id, s.pass_no, s.seq, r.source, r.source_url, r.created_at,
              r.rating, r.thread_context, r.text_raw, r.lang
       FROM gold_sample s JOIN records r USING (record_id)
       WHERE s.sitting_id = ?
         AND NOT EXISTS (SELECT 1 FROM gold g
                         WHERE g.record_id = s.record_id AND g.pass_no = s.pass_no)
       ORDER BY s.seq LIMIT 1""", (sitting,)).fetchone()

if nxt is None:
    st.success(f"**{sitting} complete** — {done}/{total} labelled.", icon="✅")
    if d1 == t1 and d2 == t2:
        st.balloons()
        st.info("Both sittings done. Next: `python pipeline/validate/score.py` to "
                "score the classifier against these labels, then commit `data/corpus.db`.",
                icon="➡️")
    st.stop()


# --------------------------------------------------------------------------
# The record. Text only — no model output anywhere on this page.
# --------------------------------------------------------------------------
meta = " · ".join(x for x in [
    nxt["source"],
    (nxt["created_at"] or "")[:10] or None,
    f"{nxt['rating']}★" if nxt["rating"] else None,
    nxt["lang"],
] if x)
st.caption(f"Item {nxt['seq']} of {total}  ·  {meta}")
if nxt["thread_context"]:
    st.caption(f"Context: {nxt['thread_context']}")

# text_raw is verbatim user content and is NOT trusted markup. Escaping is what
# stops a record containing "<script>" or stray angle brackets from rendering as
# HTML — and it keeps the labeller reading exactly what the classifier read.
st.markdown(
    "<div style='background:rgba(128,128,128,.10);padding:1.1rem 1.3rem;"
    "border-radius:.5rem;font-size:1.06rem;line-height:1.6;white-space:pre-wrap'>"
    f"{html.escape(nxt['text_raw'])}</div>", unsafe_allow_html=True)
st.caption(f"[source]({nxt['source_url']})")

st.divider()

with st.form(f"label-{nxt['record_id']}-{nxt['pass_no']}", clear_on_submit=True):
    rel = st.radio(
        "**Is this relevant?** — does it say something about why a person did "
        "*not* buy something they were considering online, in fashion?",
        ["Relevant", "Not relevant"], horizontal=True, index=None)

    st.caption("Leave codes empty if not relevant. Assign every code that genuinely "
               "applies — multi-label is expected; the average record carries ~1.5.")

    picked: list[str] = []
    tabs = st.tabs([STAGE_NAMES[s] for s in "ABCD"])
    for tab, stage in zip(tabs, "ABCD"):
        with tab:
            for c in sorted([x for x in CODES if x["stage"] == stage],
                            key=lambda d: d["journey_rank"]):
                if st.checkbox(f"**{c['id']}** — {c['name']}",
                               key=f"c_{nxt['record_id']}_{nxt['pass_no']}_{c['id']}",
                               help=c.get("boundary_note")):
                    picked.append(c["id"])

    seg = st.selectbox(
        "**Segment** — leave blank if the text does not support one",
        [None] + list(SEGMENTS), format_func=lambda k: "—" if k is None else SEGMENTS[k])

    notes = st.text_area(
        "Notes", placeholder="Anything ambiguous, any boundary that felt wrong, and "
                             "— per EC-VAL-5 — any amendment, with the reason.")

    submitted = st.form_submit_button("Save and next →", type="primary")

if submitted:
    if rel is None:
        st.error("Choose relevant or not relevant.")
        st.stop()
    is_rel = int(rel == "Relevant")
    codes = picked if is_rel else []
    if is_rel and not codes:
        codes = ["Z-99"]   # EC-CLS-1 applies to humans too: relevant but uncodeable
                           # is a real answer, and it is the AC-11 signal
    con.execute(
        "INSERT OR REPLACE INTO gold (record_id, pass_no, sitting_id, stratum,"
        " is_relevant, codes, segment, labelled_at, notes) VALUES (?,?,?,?,?,?,?,?,?)",
        (nxt["record_id"], nxt["pass_no"], sitting,
         con.execute("SELECT stratum FROM gold_sample WHERE record_id=? AND pass_no=?",
                     (nxt["record_id"], nxt["pass_no"])).fetchone()[0],
         is_rel, json.dumps(codes), str(seg) if seg else None,
         datetime.now(timezone.utc).isoformat(timespec="seconds"),
         notes.strip() or None))
    con.commit()
    st.rerun()
