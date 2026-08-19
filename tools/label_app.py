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

The same reasoning rules out the obvious speed-ups. Codes are NEVER reordered
by likelihood, pre-ticked, or filtered to a shortlist: each would put a
suggestion in front of the labeller and inflate agreement while looking like
an ergonomics win. The layout below is fast because nothing moves and
everything is on one screen — not because it hints.

WHY IT LIVES OUTSIDE `app/` AND REFUSES TO RUN ON STREAMLIT CLOUD
-----------------------------------------------------------------
implementationplan.md 2.9 names this `app/pages/9_Label.py`, but §0.5 pins
the public nav to four sections and Streamlit auto-discovers everything in
`app/pages/`. Left there it would show an evaluator a fifth entry that only
errors. It is an operator tool, not a project section, so it runs as its own
local app: `streamlit run tools/label_app.py`.

Streamlit Community Cloud also rebuilds its filesystem on every push, so a
label written there is lost with no error. This refuses to run under
/mount/src and exports JSON on demand, because hours of human judgement
should never exist in exactly one place.

PROTOCOL (Appendix B / EC-VAL-1)
--------------------------------
Two sittings. Twenty sitting-1 records reappear in sitting 2 without being
marked as repeats — that is T-13, intra-rater agreement, and it only means
anything if the labeller cannot tell. Do not go looking for them.

Where the model looks right and the human looks wrong, the gold label MAY be
amended — but only with the reason written into `notes` (EC-VAL-5). Gold is
one person's judgement recorded honestly, not ground truth handed down. The
Revise tab exists for exactly that, and it requires the reason.
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "corpus.db"

st.set_page_config(page_title="Gold labelling", page_icon="✍️", layout="wide",
                   initial_sidebar_state="expanded")


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
        "The labels land in `data/corpus.db` in your working copy and are "
        "committed like any other artefact.",
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
        ok = st.form_submit_button("Unlock")
    # st.rerun() must be called OUTSIDE the form block, and a wrong password
    # must say so. Both were wrong here, and both presented identically: you
    # type the password, press Enter, and nothing at all happens.
    if ok:
        if pw == want:
            st.session_state["label_ok"] = True
            st.rerun()
        st.error("That password does not match `LABEL_PASSWORD` in "
                 "`.streamlit/secrets.toml`.", icon="🔒")
    return False


if not _gate():
    st.stop()


# --------------------------------------------------------------------------
# Data
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
BY_ID = {c["id"]: c for c in CODES}
BY_STAGE = {s: sorted([c for c in CODES if c["stage"] == s],
                      key=lambda d: d["journey_rank"]) for s in "ABCD"}
STAGE_LABEL = {"A": "A · Recall / Discovery", "B": "B · Wishlist / Navigation",
               "C": "C · Confidence & Decision", "D": "D · Checkout / Conversion"}
SEGMENTS = {
    1: "① Collectors — saving as browsing, no purchase intent",
    2: "② Lapsed Intenders — intent existed, has since died",
    3: "③ Ready Buyers — intent live, no unresolved doubt",
    4: "④ Stuck Deciders — intent live, doubt voiced and unresolved",
    5: "⑤ Committed Waiters — waiting on a named external condition",
    6: "⑥ Hesitant Waiters — waiting, condition vague or self-imposed",
}
NOT_RELEVANT_WORDS = {"n", "no", "nr", "x", "-", "na", "none"}
SITTINGS = ("sitting-1", "sitting-2")

if con.execute("SELECT count(*) FROM gold_sample").fetchone()[0] == 0:
    st.error("No sampling frame. Run `python pipeline/validate/goldset.py` first.", icon="⚠️")
    st.stop()


def parse_codes(raw: str) -> tuple[list[str], list[str], bool]:
    """'c1 c6' -> (['C1','C6'], [], False). Returns (valid, unknown, not_relevant).

    Typing is the fast path, so it must be forgiving about case and separators
    and strict about everything else: an unrecognised token is reported rather
    than dropped, because a silently ignored code is a wrong label that looks
    like a right one.
    """
    toks = [t for t in re.split(r"[\s,;]+", raw.strip()) if t]
    if len(toks) == 1 and toks[0].lower() in NOT_RELEVANT_WORDS:
        return [], [], True
    valid, unknown = [], []
    for t in toks:
        key = t.upper().replace("_", ".")
        if key in BY_ID:
            if key not in valid:
                valid.append(key)
        else:
            unknown.append(t)
    return valid, unknown, False


def counts(sitting: str) -> tuple[int, int, int]:
    total = con.execute("SELECT count(*) FROM gold_sample WHERE sitting_id=?",
                        (sitting,)).fetchone()[0]
    done = con.execute(
        "SELECT count(*) FROM gold_sample s JOIN gold g"
        " ON g.record_id=s.record_id AND g.pass_no=s.pass_no"
        " WHERE s.sitting_id=?", (sitting,)).fetchone()[0]
    skipped = con.execute(
        "SELECT count(*) FROM gold_sample s JOIN gold_skip k"
        " ON k.record_id=s.record_id AND k.pass_no=s.pass_no"
        " WHERE s.sitting_id=?", (sitting,)).fetchone()[0]
    return done, total, skipped


def skip(rec_id: str, pass_no: int, sitting: str, reason: str | None) -> None:
    """Record the skip rather than passing over it. See schema.sql: a skip is
    evidence, and an unrecorded one silently biases the sample toward the easy
    records."""
    stratum = con.execute("SELECT stratum FROM gold_sample WHERE record_id=? AND pass_no=?",
                          (rec_id, pass_no)).fetchone()[0]
    con.execute(
        "INSERT OR REPLACE INTO gold_skip (record_id, pass_no, sitting_id, stratum,"
        " reason, skipped_at) VALUES (?,?,?,?,?,?)",
        (rec_id, pass_no, sitting, stratum, (reason or "").strip() or None,
         datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()


def save(rec_id: str, pass_no: int, sitting: str, is_rel: int,
         codes: list[str], seg, notes: str | None) -> None:
    stratum = con.execute("SELECT stratum FROM gold_sample WHERE record_id=? AND pass_no=?",
                          (rec_id, pass_no)).fetchone()[0]
    con.execute(
        "INSERT OR REPLACE INTO gold (record_id, pass_no, sitting_id, stratum,"
        " is_relevant, codes, segment, labelled_at, notes) VALUES (?,?,?,?,?,?,?,?,?)",
        (rec_id, pass_no, sitting, stratum, is_rel, json.dumps(codes),
         str(seg) if seg else None,
         datetime.now(timezone.utc).isoformat(timespec="seconds"), notes))
    con.commit()


def render_record(r: sqlite3.Row) -> None:
    meta = " · ".join(x for x in [
        r["source"], (r["created_at"] or "")[:10] or None,
        f"{r['rating']}★" if r["rating"] else None, r["lang"]] if x)
    st.caption(meta)
    if r["thread_context"]:
        st.caption(f"Context: {r['thread_context']}")
    # Capped height: the record must never push the controls off-screen. A
    # layout where Save moves depending on text length is what produced
    # mis-grades in the first version.
    st.markdown(
        "<div style='background:rgba(128,128,128,.10);padding:1rem 1.2rem;"
        "border-radius:.5rem;font-size:1.05rem;line-height:1.6;white-space:pre-wrap;"
        "max-height:58vh;overflow-y:auto'>"
        f"{html.escape(r['text_raw'])}</div>", unsafe_allow_html=True)
    st.caption(f"[source]({r['source_url']})")


def code_reference() -> None:
    with st.expander("Code reference — full names and boundary notes"):
        for s in "ABCD":
            st.markdown(f"**{STAGE_LABEL[s]}**")
            for c in BY_STAGE[s]:
                st.markdown(f"- **{c['id']}** — {c['name']}  \n"
                            f"  <span style='opacity:.65;font-size:.86rem'>"
                            f"{html.escape(str(c.get('boundary_note') or ''))}</span>",
                            unsafe_allow_html=True)


def code_picker(key_prefix: str, preset: list[str]) -> list[str]:
    """Pills, grouped by stage, every code always visible in a fixed position.
    Never reordered or filtered — see the module docstring."""
    picked: list[str] = []
    for s in "ABCD":
        opts = [c["id"] for c in BY_STAGE[s]]
        sel = st.pills(
            STAGE_LABEL[s], opts,
            selection_mode="multi",
            default=[c for c in preset if c in opts],
            key=f"{key_prefix}_pills_{s}",
            format_func=lambda cid: f"{cid} · {BY_ID[cid]['name'][:26]}")
        picked += list(sel or [])
    return picked


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Sitting")
    sitting = st.radio("Sitting", list(SITTINGS), label_visibility="collapsed")
    d1, t1, k1 = counts(SITTINGS[0])
    d2, t2, k2 = counts(SITTINGS[1])
    st.progress((d1 + k1) / max(t1, 1), text=f"sitting-1 · {d1}/{t1}"
                + (f"  ({k1} skipped)" if k1 else ""))
    st.progress((d2 + k2) / max(t2, 1), text=f"sitting-2 · {d2}/{t2}"
                + (f"  ({k2} skipped)" if k2 else ""))
    if (k1 + k2) and (k1 + k2) / max(d1 + d2 + k1 + k2, 1) > 0.15:
        st.warning(f"{k1 + k2} skipped — over 15% of what you have seen. The hard\n                   strata are over-sampled on purpose, so a high skip rate thins\n                   exactly the cases the metrics need. Worth a look at which.",
                   icon="⚠️")
    if sitting == SITTINGS[1] and d1 < t1:
        st.warning(f"Sitting 1 has {t1 - d1} left. The split exists so intra-rater "
                   "drift is measurable — finish sitting 1 first.", icon="⏳")
    st.divider()
    st.caption("**Fast path:** type codes and press Enter — `c1 c6`. "
               "Type `n` for not relevant. Clicking the chips works too.")
    st.divider()
    n_skipped = con.execute("SELECT count(*) FROM gold_skip").fetchone()[0]
    if n_skipped:
        # Skipped records are set aside, never discarded. Coming back to them
        # with fresh eyes is how the over-sampled hard strata stay populated.
        if st.button(f"↩ Put {n_skipped} skipped back in the queue", width="stretch"):
            con.execute("DELETE FROM gold_skip")
            con.commit()
            st.rerun()
        with st.expander("What was skipped"):
            for r in con.execute(
                    """SELECT s.seq, k.stratum, k.reason FROM gold_skip k
                       JOIN gold_sample s ON s.record_id=k.record_id
                        AND s.pass_no=k.pass_no ORDER BY s.seq"""):
                st.caption(f"item {r['seq']} · {r['stratum']}"
                           + (f" · {r['reason']}" if r["reason"] else ""))
        st.divider()

    rows = [dict(r) for r in con.execute("SELECT * FROM gold ORDER BY labelled_at")]
    st.download_button(f"⬇ Export {len(rows)} labels (JSON)",
                       json.dumps(rows, indent=2), file_name="gold_backup.json",
                       mime="application/json", disabled=not rows, width="stretch")

tab_label, tab_revise = st.tabs(["Label", f"Revise ({len(rows)} done)"])


# --------------------------------------------------------------------------
# Label
# --------------------------------------------------------------------------
with tab_label:
    done, total, skipped = counts(sitting)
    nxt = con.execute(
        """SELECT s.record_id, s.pass_no, s.seq, r.source, r.source_url, r.created_at,
                  r.rating, r.thread_context, r.text_raw, r.lang
           FROM gold_sample s JOIN records r USING (record_id)
           WHERE s.sitting_id = ?
             AND NOT EXISTS (SELECT 1 FROM gold g
                             WHERE g.record_id = s.record_id AND g.pass_no = s.pass_no)
             AND NOT EXISTS (SELECT 1 FROM gold_skip k
                             WHERE k.record_id = s.record_id AND k.pass_no = s.pass_no)
           ORDER BY s.seq LIMIT 1""", (sitting,)).fetchone()

    if nxt is None:
        st.success(f"**{sitting} complete** — {done}/{total} labelled.", icon="✅")
        if d1 == t1 and d2 == t2:
            st.balloons()
        st.info("Next: score the classifier against these labels, then commit "
                "`data/corpus.db`.", icon="➡️")
    else:
        st.progress((done + skipped) / max(total, 1),
                    text=f"{done} of {total} labelled · item {nxt['seq']}"
                         + (f" · {skipped} skipped" if skipped else ""))
        left, right = st.columns([1.15, 1], gap="large")
        with left:
            render_record(nxt)
        with right:
            fkey = f"lab-{nxt['record_id']}-{nxt['pass_no']}"
            with st.form(fkey, clear_on_submit=True):
                # Save sits ABOVE the codes, so it is in the same place on every
                # record regardless of how long the text or the code list is.
                bcol, scol = st.columns([2, 1])
                with bcol:
                    submitted = st.form_submit_button("Save and next →", type="primary",
                                                      width="stretch")
                with scol:
                    # Skipping beats guessing: a guess adds noise that is
                    # indistinguishable from classifier error downstream.
                    skipped_btn = st.form_submit_button(
                        "Skip ⏭", width="stretch",
                        help="Use this whenever you genuinely cannot tell. It is "
                             "recorded with your reason and excluded from the "
                             "agreement metrics — never guess to fill a row.")
                typed = st.text_input(
                    "Codes — type and press Enter",
                    placeholder="c1 c6    ·    n = not relevant",
                    key=f"{fkey}_typed")
                rel_override = st.segmented_control(
                    "Relevance", ["Relevant", "Not relevant"],
                    default=None, key=f"{fkey}_rel",
                    help="Only needed when you assign no codes. Assigning any "
                         "code implies relevant.")
                picked = code_picker(fkey, [])
                with st.expander("Segment and notes (optional)"):
                    seg = st.selectbox(
                        "Segment", [None] + list(SEGMENTS),
                        format_func=lambda k: "—" if k is None else SEGMENTS[k],
                        key=f"{fkey}_seg")
                    notes = st.text_area(
                        "Notes", key=f"{fkey}_notes",
                        placeholder="Ambiguity, a boundary that felt wrong, or an "
                                    "amendment with its reason (EC-VAL-5).")

            if skipped_btn:
                skip(nxt["record_id"], nxt["pass_no"], sitting, notes)
                st.rerun()

            if submitted:
                typed_codes, unknown, typed_nr = parse_codes(typed)
                codes = list(dict.fromkeys(list(picked) + typed_codes))
                if unknown:
                    st.error(f"Unrecognised: {', '.join(unknown)} — nothing saved.")
                elif typed_nr or (not codes and rel_override == "Not relevant"):
                    save(nxt["record_id"], nxt["pass_no"], sitting, 0, [], None,
                         (notes or "").strip() or None)
                    st.rerun()
                elif codes:
                    save(nxt["record_id"], nxt["pass_no"], sitting, 1, codes, seg,
                         (notes or "").strip() or None)
                    st.rerun()
                elif rel_override == "Relevant":
                    # Relevant but uncodeable is a real answer, and it is the
                    # AC-11 signal rather than a gap to be tidied away.
                    save(nxt["record_id"], nxt["pass_no"], sitting, 1, ["Z-99"], seg,
                         (notes or "").strip() or None)
                    st.rerun()
                else:
                    st.error("Enter codes, or `n`, or pick a relevance.")

        code_reference()


# --------------------------------------------------------------------------
# Revise — EC-VAL-5. Amendments are recorded, never silent.
# --------------------------------------------------------------------------
with tab_revise:
    if not rows:
        st.info("Nothing labelled yet.")
    else:
        st.caption("Correcting a grade is expected and is part of the protocol. "
                   "EC-VAL-5 requires the reason, so the note is mandatory here — "
                   "a gold set that was quietly edited cannot be defended.")
        labelled = con.execute(
            """SELECT g.record_id, g.pass_no, g.is_relevant, g.codes, g.segment,
                      g.notes, s.seq, s.sitting_id, r.text_raw, r.source,
                      r.source_url, r.created_at, r.rating, r.thread_context, r.lang
               FROM gold g
               JOIN gold_sample s ON s.record_id=g.record_id AND s.pass_no=g.pass_no
               JOIN records r ON r.record_id=g.record_id
               ORDER BY s.sitting_id, s.seq""").fetchall()
        opts = {f"{r['sitting_id']} · item {r['seq']} · "
                f"{'relevant: ' + (', '.join(json.loads(r['codes'])) or 'Z-99') if r['is_relevant'] else 'not relevant'}": r
                for r in labelled}
        choice = st.selectbox("Record to revise", list(opts))
        r = opts[choice]

        left, right = st.columns([1.15, 1], gap="large")
        with left:
            render_record(r)
        with right:
            rkey = f"rev-{r['record_id']}-{r['pass_no']}"
            existing = json.loads(r["codes"])
            with st.form(rkey):
                save_rev = st.form_submit_button("Save correction", type="primary",
                                                 width="stretch")
                typed = st.text_input("Codes — type and press Enter",
                                      placeholder="c1 c6  ·  n = not relevant",
                                      key=f"{rkey}_typed")
                rel_override = st.segmented_control(
                    "Relevance", ["Relevant", "Not relevant"],
                    default="Relevant" if r["is_relevant"] else "Not relevant",
                    key=f"{rkey}_rel")
                picked = code_picker(rkey, [c for c in existing if c in BY_ID])
                seg = st.selectbox(
                    "Segment", [None] + list(SEGMENTS),
                    index=(list(SEGMENTS).index(int(r["segment"])) + 1) if r["segment"] else 0,
                    format_func=lambda k: "—" if k is None else SEGMENTS[k],
                    key=f"{rkey}_seg")
                reason = st.text_area("Reason for the change — required",
                                      value=r["notes"] or "", key=f"{rkey}_reason")

            if save_rev:
                typed_codes, unknown, typed_nr = parse_codes(typed)
                codes = list(dict.fromkeys(list(picked) + typed_codes))
                if not reason.strip():
                    st.error("EC-VAL-5: give the reason for the amendment.")
                elif unknown:
                    st.error(f"Unrecognised: {', '.join(unknown)} — nothing saved.")
                else:
                    is_rel = 0 if (typed_nr or rel_override == "Not relevant") else 1
                    save(r["record_id"], r["pass_no"], r["sitting_id"], is_rel,
                         [] if not is_rel else (codes or ["Z-99"]),
                         None if not is_rel else seg, reason.strip())
                    st.success("Amended and recorded.")
                    st.rerun()

        code_reference()
