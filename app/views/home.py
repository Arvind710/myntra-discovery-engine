"""Home — orientation only. What this is, how it works, where to go next.

WHY THIS PAGE IS SHORT
----------------------
It has had two wrong shapes. First it led with the answer, which asks a reader
to trust a ranking before they know how it was produced. Then it became the
method in full -- eight sections, every check and caveat -- which is the right
material in the wrong place: a first-time reader does not need the inversion
threshold before they know what the app is for.

Home is the map. It states the goal, shows the five moves the engine makes to
reach it, and says what each section answers. Everything that argues a case now
lives in the section that owns that case: the corpus and its filters on Data
Bank, the journey and the choice of step on Analysis, the segment and the
ranking on Insights.

The rule for anything added here later: if it is evidence, it belongs in a
section. Home carries only what someone needs in order to know where to click.
"""

from pathlib import Path

import streamlit as st

from lib import db, story as S

VIEWS = Path(__file__).resolve().parent

st.title("Where is the biggest opportunity in wishlisting?")
st.caption("People save things and don't buy them. This engine reads public conversation "
           "at scale to find out where that breaks down, and which group of shoppers is "
           "worth building for.")

st.markdown(
    "It is a **discovery instrument, not a dashboard.** It takes one question — *why "
    "don't people buy what they saved?* — and narrows it, in five steps, to a single "
    "barrier and a single group, each with its evidence and its caveats attached.")

# --------------------------------------------------------------- the process
# Five cards with arrows between them, one line each. This is the whole argument
# of the app in the order it is made, and it is the only thing on Home that is
# not navigation. Rendered as one flex row rather than st.columns because the
# arrows are the content: these are moves in sequence, not parallel features.
STEPS = [
    ("Read", "12,002 public comments, posts and reviews — then cut to the ones about "
             "saving and buying", "#0072B2"),
    ("Break it down", "Split wishlisting into the four things a saved item has to "
                      "survive before it is bought", "#56B4E9"),
    ("Pick the step", "Find which of the four the conversation is really about — and "
                      "test that it is not just the loudest", "#E69F00"),
    ("Segment", "Inside that step, group people by intent, timing, and whether they "
                "have decided", "#009E73"),
    ("Rank", "Score every barrier on size, evidence, and whether it can be fixed "
             "without a discount", "#CC79A7"),
]
cards = []
for i, (title, line, colour) in enumerate(STEPS, 1):
    cards.append(
        f"<div style='flex:1;min-width:135px;display:flex;flex-direction:column;"
        f"border-top:5px solid {colour};padding:.55rem .45rem 0 0'>"
        f"<div style='font-size:.66rem;letter-spacing:.1em;color:#8a8a8a'>{i}</div>"
        f"<div style='font-weight:700;font-size:1rem;margin:.1rem 0 .2rem'>{title}</div>"
        f"<div style='font-size:.82rem;color:#9a9a9a;line-height:1.35'>{line}</div></div>")
arrow = ("<div style='align-self:center;color:#6a6a6a;font-size:1.3rem;"
         "padding:0 .3rem'>&rsaquo;</div>")
st.html("<div style='display:flex;flex-wrap:wrap;gap:.2rem;margin:1rem 0 .6rem'>"
        + arrow.join(cards) + "</div>")

# ---------------------------------------------------------------- the result
# One line on where it landed. A reader who has just been shown the method will
# ask what it produced, and making them hunt for it is its own kind of unclear.
# Read from the same tables the sections read, so it cannot drift from them.
if db.corpus_is_populated():
    rec = db.query("SELECT segment_name, n, share FROM analysis_segment_recommendation "
                   "WHERE recommended = 1")
    opp = db.query("SELECT code, n FROM analysis_opportunity WHERE rank = 1")
    if not rec.empty and not opp.empty:
        r, o = rec.iloc[0], opp.iloc[0]
        st.success(
            f"**Where it lands:** the step is **{S.stage_title('C')}**, the group is "
            f"**{r['segment_name']}** ({int(r['n'])} people, {float(r['share']):.0%} of "
            f"the winnable population), and the barrier to solve first is "
            f"**“{S.voice(o['code'])}”** ({int(o['n'])} records). How each of those was "
            "decided, and what would overturn it, is in the sections below.", icon="🎯")

st.warning(S.PROXY_WARNING, icon="⚠️")

# ------------------------------------------------------------- where to go
st.subheader("Where to find what")

SECTIONS = [
    ("data_bank.py", "🗄️", "Data Bank", "What was read, and what was thrown away",
     "Every record, its source, and the reason anything was set aside — including the "
     "rule that decides what counts as relevant, in full. Start here if your first "
     "question is *where did this data come from?*"),
    ("analysis.py", "📊", "Analysis", "The four steps, and which one breaks",
     "Wishlisting broken into a journey, every barrier at every step in the shopper's "
     "own words, and the test that the busiest step is not merely the loudest."),
    ("insights.py", "💡", "Insights", "Who to build for, and what to fix first",
     "The six segments and why one was chosen, the opportunity score and what it is "
     "made of, how far the ranking moves when you change the weights, and what would "
     "prove it wrong."),
    ("ask.py", "💬", "Ask", "Interrogate it in your own words",
     "A chatbot answering only from this corpus, with citations — and refusing, out "
     "loud, when the corpus cannot support an answer."),
]
for path, icon, name, tagline, blurb in SECTIONS:
    with st.container(border=True):
        a, b = st.columns([1, 3])
        with a:
            st.page_link(str(VIEWS / path), label=f"**{name}**", icon=icon)
            st.caption(tagline)
        b.markdown(blurb)

st.caption("Public data only · authors pseudonymised · no personal information in outputs.")
