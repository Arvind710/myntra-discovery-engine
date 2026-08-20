"""The vocabulary layer — how the app says things to someone who has never
read the codebook.

WHY THIS EXISTS
---------------
Every page used to lead with a code id: "C2 · 241 records · 0.237". That is
readable to whoever wrote the codebook and to nobody else. A code id is an
index, not a description, and a share with no explanation of its denominator is
a number a reader cannot argue with — which is the opposite of what this
project claims to be for.

So one module owns the answer to "what do we call this, and how do we explain
it", and every view reads from here. Three rules follow from that:

  1. THE PLAIN NAME LEADS, the code follows in small type. A reader who never
     learns a single code id should still be able to use the whole app.
  2. EVERY METRIC CARRIES ITS OWN EXPLANATION. `explain()` is not a tooltip
     afterthought — a number whose meaning has to be inferred will be
     misread, and this corpus is unusually easy to misread as a funnel.
  3. THE JOURNEY IS THE STRUCTURE. Stages A-D are not four buckets, they are
     four things that must go right in sequence, and the codes are the ways
     each one fails. Presenting the codes as a flat ranked list loses the only
     thing that makes them interpretable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from lib import framework as F

ROOT = Path(__file__).resolve().parents[2]

STAGE_ORDER = ["A", "B", "C", "D"]

# Okabe-Ito, one hue per stage, held consistent everywhere a stage appears.
STAGE_COLOUR = {"A": "#0072B2", "B": "#56B4E9", "C": "#E69F00", "D": "#009E73",
                "Z": "#8C8C8C"}


@lru_cache(maxsize=1)
def _doc() -> dict:
    return yaml.safe_load((ROOT / "codebook" / "plain_language.yaml").read_text())


@lru_cache(maxsize=1)
def stages() -> dict:
    return _doc()["stages"]


def stage_title(stage: str) -> str:
    return stages().get(stage, {}).get("title", stage)


def stage_of(code: str) -> str:
    return "Z" if str(code).startswith("Z") else str(code)[0]


@lru_cache(maxsize=256)
def voice(code: str) -> str:
    """The barrier in the user's own words. THIS is the chart label."""
    return _doc()["codes"].get(code, {}).get("voice", "")


@lru_cache(maxsize=256)
def plain(code: str) -> str:
    """One line on the mechanism — what is actually going wrong."""
    return " ".join(str(_doc()["codes"].get(code, {}).get("plain", "")).split())


@lru_cache(maxsize=256)
def name(code: str) -> str:
    """The short analytic name, e.g. 'Fit & size uncertainty'."""
    return F.name_of(code) or code


@lru_cache(maxsize=256)
def tag(code: str) -> str:
    """The framework code, for readers who DO want the id. Always secondary."""
    return F.to_framework(code)


def chart_label(code: str, width: int = 46) -> str:
    """What goes on an axis: the user's words, truncated, code appended small.

    Deliberately NOT `f"{code} · {name}"`. The axis of a bar chart is the one
    place a reader looks first, and spending it on an index they cannot decode
    wastes the most valuable space on the page.
    """
    v = voice(code) or name(code)
    if len(v) > width:
        v = v[: width - 1].rstrip(" ,.;") + "…"
    return f"{v}  ({tag(code)})"


# ---------------------------------------------------------------- metrics
# Every one of these is written to be read by someone who has not seen the
# methodology. Where a metric is easy to misread, the explanation says what it
# is NOT before it says what it is.
METRICS: dict[str, str] = {
    "share": (
        "**Share of discussion.** Out of every relevant record in the corpus, this "
        "is the fraction that mentions this barrier. It is **not** the share of "
        "shoppers who hit it, and **not** a drop-off rate — we have no user-level "
        "data. It measures how much something is *talked about*."
    ),
    "n": (
        "**How many records.** One record is one comment, post or review. Below "
        "30 we show the count but never rank it, because a handful of records "
        "cannot support a claim about which barrier is bigger."
    ),
    "authors": (
        "**How many different people.** 200 records from 12 people is a much "
        "weaker claim than 200 from 180, so the two counts are always shown "
        "together."
    ),
    "lift": (
        "**How distinctive, not how common.** 2.0× means people in this group "
        "raise this barrier twice as often as the corpus overall. A barrier at "
        "1.0× is equally common everywhere and tells you nothing about who to "
        "build for — it is the lift, not the size, that makes a group worth "
        "targeting."
    ),
    "confidence": (
        "**How sure the classifier was**, 0 to 1, averaged across the records. "
        "Low confidence does not mean the barrier is not real; it means the "
        "wording was ambiguous and the label should be leaned on less."
    ),
    "cooccurrence": (
        "**Two barriers that travel together.** Lift well above 1 means they "
        "appear in the same record far more often than chance would produce — "
        "evidence they are one compound problem with one fix, rather than two "
        "separate ones."
    ),
    "workaround": (
        "**Effort spent working around it.** Someone who orders two sizes, or "
        "hunts for buyer photos, is proving the need exists without being asked. "
        "This is stronger evidence than complaint volume, which mostly measures "
        "how annoying something is to talk about."
    ),
    "counterfactual": (
        "**They named their own unblock** — “I'd have bought it if…”. The most "
        "directly actionable signal in the corpus, and the rarest."
    ),
    "defer": (
        "**Intent survived.** *Defer* means they still want it and postponed; "
        "*exit* means the intent was destroyed. Deferred shoppers are the "
        "winnable population — exits mostly are not."
    ),
    "evidence_strength": (
        "**How well-supported, independent of size.** Combines how many sources "
        "carry it, how often people work around it, how often they name their own "
        "unblock, and classifier confidence. It downgrades a barrier carried by "
        "one platform and upgrades one corroborated across four."
    ),
    "solvable": (
        "**Can it be fixed without money?** The assignment forbids discounts, "
        "coupons and cashback. A barrier that can only be solved by dropping the "
        "price scores zero here, which is why price ranks lower than its size "
        "alone would put it."
    ),
    "segment_fit": (
        "**How characteristic of the target group.** Partly circular by "
        "construction — the groups are defined by which doubts people have, so a "
        "doubt is bound to concentrate in the groups that have doubts. Set the "
        "weight to zero to see the ranking without it."
    ),
    "residual": (
        "**Relevant but unmatched.** Records that bear on the decision but fit "
        "none of the pre-registered barriers. It is the honesty valve: if this "
        "were large, the codebook would be missing something real."
    ),
}


def explain(key: str) -> str:
    return METRICS.get(key, "")


# --------------------------------------------------------------- segments
# The segments are NOT a second, parallel classification. They fall out of
# Stage C: whether a person has an unresolved doubt is exactly what "decided"
# means, and that is what separates the groups. Saying so is what makes the
# segment page comprehensible instead of arbitrary.
SEGMENT_DERIVATION = (
    "These groups are **derived, not guessed**. Three questions are asked of "
    "every record, and all three are answered by the classification that already "
    "happened:\n\n"
    "1. **Is there any intent to buy?** — no intent means a collector.\n"
    "2. **Soon, or later?** — waiting on a price, a restock or an occasion "
    "means later.\n"
    "3. **Have they decided?** — and this is the link to the journey: *any "
    "unresolved doubt from* **Deciding on the item** *means they have not "
    "decided.* A voiced doubt IS an undecided decision.\n\n"
    "That is why the groups below are a re-cut of the same evidence rather than "
    "a new opinion, and why coverage is 100% where an earlier motivation-based "
    "segmentation reached 6.6%."
)

SEGMENT_BLURB = {
    1: "Saved it as reference or inspiration. No purchase was ever intended — "
       "converting them is not a goal.",
    2: "They meant to buy, and the intent lapsed. Bought elsewhere, or the "
       "want faded.",
    3: "Intent, soon, nothing unresolved. If they have not bought, the reason "
       "is not a doubt.",
    4: "Intent, soon, **and a doubt still in the way.** The winnable group: "
       "they want it, they want it now, and something specific is stopping them.",
    5: "They have decided, and are waiting on a condition — a sale, a restock, "
       "an occasion.",
    6: "Waiting, and still unsure. Both a timing problem and a doubt.",
}


def segment_label(sid: int) -> str:
    return F.SEGMENTS.get(sid, (str(sid), ""))[0]


def segment_blurb(sid: int) -> str:
    return SEGMENT_BLURB.get(sid, F.SEGMENTS.get(sid, ("", ""))[1])


# ------------------------------------------------------------- the model
# One paragraph that has to do more work than any other on the site: it is what
# makes every number downstream legible. Kept short on purpose.
THE_MODEL = (
    "A saved item has to survive **four things** before it is bought. The person has "
    "to come back to the list, find the item again, resolve whatever doubt they have "
    "about it, and get through checkout. Each of those can fail in specific ways, and "
    "those ways are what this engine counts."
)

PROXY_WARNING = (
    "**Everything here is a share of conversation, not a drop-off rate.** This project "
    "has no access to Myntra's analytics. It reads what people say in public — so it "
    "measures what gets *talked about*, weighted by how hard people work around it. "
    "Barriers nobody posts about are under-counted by construction, and the biggest of "
    "those is forgetting."
)
