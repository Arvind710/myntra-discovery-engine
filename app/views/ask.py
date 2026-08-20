"""Ask — the research analyst.

WHAT THIS PAGE HAS TO MAKE VISIBLE
----------------------------------
Three things, none of which are the answer text:

1. **What the question was understood to be.** A misread question answered
   confidently is the worst failure this engine can produce, because nothing
   about the output looks wrong. The restatement is printed ABOVE the answer,
   where it can still be caught (AR-6).

2. **Whether the engine answered, half-answered, or declined** — and that this
   was decided by code before any writing happened, not by the model's mood.
   The three routes are the distinguishing feature (FR-4.3); hiding them would
   throw away the thing worth showing.

3. **Where every claim came from.** Citations are rendered as numbered
   references rather than left inline: `[[analysis_code_prevalence|C1]]` in the
   middle of a sentence is machinery, and a reader who has to step over it
   stops reading. Numbered markers keep the prose readable and put the row and
   the source link one click away (AC-2).

The verification banner is shown only when verification did NOT fully pass.
A green tick on every answer trains a reader to ignore it; a banner that
appears rarely means something when it does.
"""

import html
import re

import streamlit as st

from lib import analyst as A
from lib import db, retrieval as R, story as S, verify as V

# The canonical ten (FR-4.4), in the reader's words rather than the codebook's.
SUGGESTED = [
    "What stops people from buying the things they have saved?",
    "Why do people save items to a wishlist in the first place?",
    "How much does fit and size uncertainty matter compared with price?",
    "What do people go looking for outside the app before they buy?",
    "Are people who wishlist actually intending to buy, or just bookmarking?",
    "Do different kinds of shoppers get stuck in different ways?",
]

ROUTE_LABEL = {
    "FULL":    ("✅ Answered from the corpus",
                "Everything this question needed was found in the analysed data."),
    "PARTIAL": ("⚠️ Partly answerable",
                "Some of what this question needs is in the corpus and some is not. "
                "The answer says which is which."),
    "NONE":    ("⛔ Outside this corpus",
                "This question needs data this engine does not hold. It declines "
                "rather than assembling a plausible-looking answer from adjacent "
                "records."),
}

# Human names for the tables a citation can point at, so a reference reads as
# evidence rather than as a schema.
TABLE_LABEL = {
    "analysis_code_prevalence": "how often it comes up",
    "analysis_source_code": "by source",
    "analysis_segment_code_v2": "by shopper group",
    "analysis_cooccurrence": "appears together with",
    "analysis_stage_outcome": "journey stage and outcome",
    "analysis_opportunity": "opportunity score",
    "analysis_evidence_strength": "how well-supported",
    "analysis_counterfactuals": "would have bought if",
    "analysis_workaround": "effort spent working around it",
    "analysis_addressable": "who is actually winnable",
    "analysis_stage_inversion": "how fragile the stage ranking is",
    "analysis_subcode": "finer breakdown",
    "analysis_cluster_code": "blind clusters vs the codebook",
    "analysis_weight_sensitivity": "robustness of the ranking",
    "analysis_segment_recommendation": "which group to target",
    "analysis_gold_agreement": "agreement with the human coder",
    "analysis_method_flags": "registered limitation",
    "cluster_labels": "what the blind clustering called it",
    "insights": "generated insight",
    "hypotheses": "hypothesis",
    "record": "what someone actually said",
}


def number_citations(text: str) -> tuple[str, list[dict]]:
    """Replace `[[table|key]]` with `[n]`, returning the reference list.

    Numbering follows first appearance, the way a paper does, so a reader
    scanning down the references meets them in the order the argument used
    them.
    """
    refs: list[dict] = []
    index: dict[tuple[str, str], int] = {}

    def repl(m: re.Match) -> str:
        table = "record" if m.group(1) in ("rec", "record") else m.group(1)
        key = m.group(2).strip()
        hit = index.get((table, key))
        if hit is None:
            hit = len(refs) + 1
            index[(table, key)] = hit
            refs.append({"n": hit, "table": table, "key": key})
        return f"<sup>[{hit}]</sup>"

    return (V.CITATION.sub(repl, text or ""), refs)


def _describe_key(table: str, key: str) -> str:
    """Turn a citation key into something a reader recognises."""
    if table == "record":
        return "a record in the Data Bank"
    parts = [p.strip() for p in str(key).split("|")]
    named = []
    for p in parts:
        if re.fullmatch(r"[A-DZ]\d+(\.\d+)?|Z-99", p):
            named.append(S.name(p) or p)
        elif "_" in p:
            # Flag ids and bucket names are snake_case internals. Left as-is
            # they put `proxy_not_funnel` in front of a reader, which is the
            # same mistake the readability pass removed from the other pages.
            named.append(p.replace("_", " "))
        else:
            named.append(p)
    return " · ".join(named)


def render_references(refs: list[dict], answer: "A.Answer") -> None:
    if not refs:
        return
    by_record = {r.get("record_id"): r for r in answer.records}
    rows = {(r["_cite"]["table"], str(r["_cite"]["key"])): r
            for r in answer.rows if r.get("_cite")}

    st.markdown("##### Where this came from")
    st.caption("Every numbered claim above, traced to the row or the record it "
               "rests on. Record links open the original public post.")
    for ref in refs:
        label = TABLE_LABEL.get(ref["table"], ref["table"])
        if ref["table"] == "record":
            rec = by_record.get(ref["key"])
            if rec is None:
                st.markdown(f"**[{ref['n']}]** {label} — record not in this answer's evidence")
                continue
            src = rec.get("source", "")
            url = rec.get("source_url") or ""
            span = rec.get("_span") or ""
            codes = ", ".join(S.name(c) for c in (rec.get("_codes") or []) if c)
            head = f"**[{ref['n']}]** {src}"
            if codes:
                head += f" · coded as {codes}"
            st.markdown(head + (f" · [open the original]({url})" if url else ""))
            body = span or (rec.get("text_raw") or "")[:300]
            st.markdown(f"> {html.escape(body)[:400]}")
        else:
            st.markdown(f"**[{ref['n']}]** {label} — {_describe_key(ref['table'], ref['key'])}")
            row = rows.get((ref["table"], ref["key"]))
            if row:
                shown = {k: v for k, v in row.items()
                         if not str(k).startswith("_") and k != "run_id" and v is not None}
                st.caption(" · ".join(f"{k} {v}" for k, v in list(shown.items())[:9]))


# ---------------------------------------------------------------------------

st.title("Ask the analyst")
st.caption("Ask anything about why people do not buy what they save. Answers come "
           "only from the analysed corpus — with counts, quotes, the evidence "
           "against, and a plain statement of what the data cannot show.")

status, detail = db.db_status()
if status != "ok":
    (st.error if status in ("missing", "unreadable") else st.info)(detail)
    st.stop()

# EC-OPS-4 / S4-OPS-4: a missing key degrades to a message, never a stack trace.
# The rest of the app is read-only and must stay fully usable without one.
api_key = st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
if not api_key:
    import os
    api_key = os.environ.get("OPENAI_API_KEY", "")
if not api_key:
    st.warning(
        "**The analyst is not configured on this deployment.** It needs an "
        "OpenAI key, which is not set here. Everything else — the Data Bank, "
        "the Analysis and the Insights — reads from the frozen artifacts and "
        "works normally.")
    st.stop()

with st.expander("How this answers — and when it refuses", expanded=False):
    st.markdown(
        "Each question goes through five steps. Two of them use a language "
        "model; **the other three are ordinary code**, which is what makes the "
        "guarantees below guarantees rather than instructions.\n\n"
        "1. **Read the question** and decide what evidence would settle it — "
        "including the questions you did not ask, like whether the finding "
        "survives per source.\n"
        "2. **Retrieve** from five directions at once: the counted results, "
        "verbatim records, **evidence against the emerging answer**, the "
        "method and its known biases, and published research.\n"
        "3. **Check whether that is enough** — done by comparing two lists, so "
        "refusing is a mechanical outcome rather than a judgement call.\n"
        "4. **Write the answer** under a fixed contract: counts with their "
        "denominators, quotes, counter-evidence, confidence, limitations.\n"
        "5. **Verify** — every number is matched against a retrieved row and "
        "every quote against a retrieved record, *after* writing. A number "
        "that cannot be traced is rejected and the answer is rewritten.\n\n"
        "Shares here are shares of **discussion** — how often something is "
        "raised by people who chose to post. They are never drop-off or "
        "conversion rates, and the engine has no user-level data at all.")

session_n, day_n = A.quota_state()
st.caption(f"{A.SESSION_QUESTION_CAP - session_n} questions left this session · "
           f"a public URL on a personal API budget, so the engine is rate-limited.")

if "chat" not in st.session_state:
    st.session_state["chat"] = []

if not st.session_state["chat"]:
    st.markdown("**Try one of these**")
    cols = st.columns(2)
    for i, q in enumerate(SUGGESTED):
        if cols[i % 2].button(q, key=f"sugg{i}", width="stretch"):
            st.session_state["pending"] = q
            st.rerun()

for turn in st.session_state["chat"]:
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        st.markdown(turn["rendered"], unsafe_allow_html=True)

typed = st.chat_input("Ask about the corpus…")
question = typed or st.session_state.pop("pending", None)

if question:
    with st.chat_message("user"):
        st.markdown(question)

    reject = A.screen(question)                      # EC-CHAT-7, before any cost
    blocked = A.quota_blocked()                      # EC-OPS-3
    if reject or blocked:
        with st.chat_message("assistant"):
            st.info(reject or blocked)
        st.stop()

    from openai import OpenAI
    client = OpenAI(api_key=api_key, timeout=180.0)
    con = db.connection()

    with st.chat_message("assistant"):
        with st.spinner("Planning the question, retrieving, checking the answer…"):
            history = [{"question": t["question"], "restated": t.get("restated", "")}
                       for t in st.session_state["chat"][-A.HISTORY_TURNS:]]
            answer = A.ask(client, con, question, history=history)
        A.record_question()

        if answer.error:
            st.error(f"{answer.error}\n\nNothing was charged for a failed call. "
                     "Try again, or ask a different question.")
            st.stop()

        # The restatement leads. A misread question is visible here or nowhere.
        st.markdown(f"**Understood as:** {answer.restated}")
        label, blurb = ROUTE_LABEL.get(answer.route, (answer.route, ""))
        st.caption(f"{label} — {blurb}")

        if not answer.verified:
            st.warning(
                "**Some of this answer could not be fully verified.** The "
                "engine checks every number against the rows it retrieved and "
                "every quote against the records it read; the items below did "
                "not match, and the answer is shown anyway rather than "
                "silently dropped. Treat the flagged parts as unconfirmed.\n\n"
                + "\n".join(f"- {p}" for p in (answer.report.problems()[:6]
                                               if answer.report else [])))

        rendered, refs = number_citations(answer.text)
        st.markdown(rendered, unsafe_allow_html=True)

        with st.expander(f"Evidence — {len(refs)} references", expanded=False):
            render_references(refs, answer)

        if answer.verdict and answer.verdict.caveats:
            st.caption("Too thin to rank: " + "; ".join(answer.verdict.caveats))
        st.caption(f"Two model calls · ${answer.cost_usd:.3f} · "
                   f"{answer.seconds:.0f}s · {len(answer.rows)} analysis rows and "
                   f"{len(answer.records)} records read"
                   + (" · rewritten once after verification"
                      if answer.regenerated else ""))

    st.session_state["chat"].append({
        "question": question, "restated": answer.restated,
        "rendered": (f"**Understood as:** {answer.restated}\n\n"
                     + number_citations(answer.text)[0]),
    })
