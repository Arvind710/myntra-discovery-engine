"""FR-3.4 / task 3.8 — the research instruments, pre-populated from the corpus.

Part 3 of the assignment is five or six user interviews. The engine's job is to
make sure those interviews TEST what the corpus raised rather than re-asking
what it already answered — which is what happens when a guide is written from
memory the night before.

WHY THESE ARE GENERATED RATHER THAN WRITTEN
--------------------------------------------
Every question here traces to a hypothesis, and every hypothesis carries a
falsifier. So the guide is not a list of topics; it is a list of the specific
observations that would kill each claim, arranged so a person can actually
collect them in forty minutes. If a hypothesis's falsifier is vague, that shows
up immediately as a question nobody could answer — which is useful feedback
about the hypothesis, not about the guide.

The generation is deterministic: templates over the `hypotheses` and
`analysis_*` tables. No model call, so the instruments cannot drift between
runs and cannot introduce a claim the corpus does not carry.

WHAT THE GUIDE DELIBERATELY DOES NOT DO
----------------------------------------
It does not ask "would you use a feature that…". A user asked to predict their
own behaviour will say yes, and the answer carries no information. Every
question is about a specific past event — the last time, this particular item —
because retrospective behaviour is the only thing an interview can observe.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import codebook as cbm, db as dbm  # noqa: E402

# yaml parses the codebook's `yes`/`no` into booleans; rendering those raw put
# "solvable without money: True" on a page a person is meant to read.
SOLVABLE_LABEL = {True: "yes", False: "no", "partly": "partly", "na": "n/a"}

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "artifacts"


def _fw(code: str) -> str:
    """Framework label. The app has `lib/framework`; the pipeline must not
    import from the app, so the crosswalk is read directly."""
    import yaml
    cw = yaml.safe_load((ROOT / "codebook" / "crosswalk_v2.yaml").read_text())
    m = cw["engine_to_framework"].get(code)
    return m["to"] if m else code


def load(con) -> dict:
    # Ordered by CONFIDENCE first, then evidence. Ordering by supporting_n
    # alone put the C10 hypothesis at the top of the interview guide — the one
    # resting on the code with kappa 0.10 — which is precisely the claim that
    # should not lead a research plan.
    rank = {"high": 0, "medium": 1, "low": 2}
    hyps = [dict(r) for r in con.execute("SELECT * FROM hypotheses")]
    hyps.sort(key=lambda h: (rank.get(h["confidence"], 3), -h["supporting_n"]))
    for h in hyps:
        h["codes"] = json.loads(h["codes"])
        h["verbatim_ids"] = json.loads(h["verbatim_ids"])
    ins = [dict(r) for r in con.execute(
        "SELECT * FROM insights ORDER BY novelty DESC, insight_id")]
    opp = [dict(r) for r in con.execute(
        "SELECT * FROM analysis_opportunity WHERE rank IS NOT NULL ORDER BY rank")]
    seg = con.execute(
        "SELECT * FROM analysis_segment_recommendation WHERE recommended = 1").fetchone()
    addr = {r["bucket"]: dict(r) for r in con.execute("SELECT * FROM analysis_addressable")}
    return {"hyps": hyps, "insights": ins, "opp": opp,
            "seg": dict(seg) if seg else None, "addr": addr}


def quotes(con, ids: list[str], limit: int = 3) -> list[dict]:
    """Verified spans only. A span that is not an exact substring of the record
    is not evidence and is never rendered as a quote (T-6, absolute)."""
    if not ids:
        return []
    ph = ",".join("?" * len(ids))
    return [dict(r) for r in con.execute(f"""
        SELECT DISTINCT cl.evidence_span, rec.source, rec.source_url
        FROM classifications cl JOIN records rec ON rec.record_id = cl.record_id
        WHERE cl.record_id IN ({ph}) AND cl.span_verified = 1 AND rec.text_available = 1
        LIMIT {limit}""", ids)]


# ------------------------------------------------------------ interview guide
def interview_guide(con, d: dict, cb) -> str:
    seg = d["seg"]
    L = [
        "# Interview guide — wishlist non-conversion",
        f"_Generated {date.today().isoformat()} from the corpus. "
        "Every question below exists to falsify a specific hypothesis; the hypothesis "
        "id is shown beside it._",
        "",
        "**5–6 interviews · 40 minutes · recruit people who have saved an item and not "
        "bought it within a month.**",
        "",
        "## Before you start — what this guide is for",
        "",
        "The corpus already establishes WHAT people talk about. It cannot establish "
        "**why an individual stopped**, because it only contains people who chose to "
        "post. These interviews exist to test the causal claims, and a good interview "
        "is one where a hypothesis DIES. Go in wanting that.",
        "",
        "Two rules that decide whether this is worth doing:",
        "",
        "1. **Ask about the last time, never about preferences.** \"Walk me through the "
        "last thing you saved and didn't buy\" produces evidence. \"Would you use a size "
        "guide?\" produces agreement, which is not evidence.",
        "2. **Do not describe a solution.** The moment a feature is named, the "
        "participant starts evaluating it and stops reporting what happened.",
        "",
    ]
    if seg:
        L += [f"**Recruit for segment ({seg['segment_id']}) {seg['segment_name']}** — "
              f"{seg['n']} records, {seg['share']:.1%} of the addressable population. "
              "Screen with: *have you saved something in the last two months, meant to "
              "buy it, and still not bought it?* A yes to all three is the segment.", ""]

    L += ["## 1 · Warm-up and the concrete case (8 min)", "",
          "- Tell me about the last thing you saved on a shopping app and didn't buy.",
          "- What was it? What was happening when you saved it?",
          "- Where were you in your head — buying it, or noting it?",
          "  *(This separates a live intent from a taste archive. The corpus says "
          f"{d['addr']['collectors']['share_of_corpus']:.0%} of records are the second kind, and "
          "they are not a conversion problem.)*",
          "- When did you last look at it? What made you look?",
          "",
          "## 2 · The moment it stopped (12 min)", "",
          "- Take me to the last time you had it open and didn't buy. What was on screen?",
          "- What were you trying to find out?",
          "- What did you do next — right then, in the next hour, the next day?",
          "- Did you ever go somewhere else to check something? Where? What happened after?",
          "",
          "## 3 · Falsifying the hypotheses (15 min)", "",
          "_Each block names the hypothesis it is testing and what a killing answer "
          "looks like. Cover the top three; the rest are reserve._", ""]

    for h in d["hyps"][:6]:
        codes = ", ".join(f"{_fw(c)}" for c in h["codes"])
        L += [f"### {h['hypothesis_id']} — {codes} · n={h['supporting_n']} · "
              f"confidence {h['confidence']}",
              "",
              f"> {h['statement'].split(chr(10))[0]}",
              "",
              f"**Ask:** {_questions_for(h, cb)}",
              "",
              f"**This dies if:** {h['falsifier']}",
              ""]
        qs = quotes(con, h["verbatim_ids"])
        if qs:
            L.append("**In users' words** (verified exact quotes, for your ear, not to "
                     "read aloud):")
            L += [f"> \"{q['evidence_span'].strip()}\"  — {q['source']}" for q in qs]
            L.append("")

    L += ["## 4 · The counterfactual (5 min)", "",
          "- If it had gone differently that day, would you have bought it? What "
          "would have had to be true?",
          "  *(Ask this last. Asked early it primes every previous answer. It maps to "
          "the counterfactual rate the corpus measures directly.)*",
          "- Did you buy something like it since? Where, and what was different there?",
          "",
          "## 5 · Close (2 min)", "",
          "- What's still sitting in your saved list right now that you might still buy?",
          "- Anything I should have asked?",
          "",
          "---",
          "",
          "## Interviewer's note on what would make this fail",
          "",
          "If every participant confirms every hypothesis, suspect the questions rather "
          "than celebrate. Leading questions are the most common cause, and the second "
          "most common is recruiting only people who already agree — which is exactly "
          "the bias the corpus itself has, since it contains only people who chose to "
          "post about it.",
          ]
    return "\n".join(L) + "\n"


def _questions_for(h: dict, cb) -> str:
    """Turn a falsifier into something askable. Deliberately mechanical: the
    falsifier is where the thinking happened, and paraphrasing it in a model
    would put a second, unverified claim between the evidence and the guide."""
    names = [cb.codes[c]["name"] for c in h["codes"] if c in cb.codes]
    lead = names[0].lower() if names else "this barrier"
    return (f"Ask them to describe the moment {lead} came up, in their own words, "
            f"without naming it yourself. Then ask what they did about it, and what "
            f"they would have needed to resolve it there and then. "
            f"Listen specifically for whether the falsifier condition holds.")


# --------------------------------------------------------- survey instrument
def survey(con, d: dict, cb) -> str:
    L = ["# Survey instrument — wishlist non-conversion",
         f"_Generated {date.today().isoformat()}. Screener + 12 items, ~4 minutes._",
         "",
         "## Why a survey as well as interviews",
         "",
         "Interviews establish mechanism; they cannot establish prevalence from six "
         "people. The corpus gives prevalence of *discussion*, which over-counts loud "
         "barriers and under-counts silent ones — Stage A most of all, since forgetting "
         "produces no complaint. **A survey is the only instrument here that can "
         "measure a silent barrier**, and that is its job. Item S2 exists for exactly "
         "that reason.",
         "",
         "## Screener",
         "",
         "**S0.** In the last two months, have you saved an item to a wishlist or "
         "shopping list and not bought it? → *No: terminate.*",
         "",
         "**S1.** When you saved it, which was closest to true? "
         "*(single choice — this is the segment assignment, and it must come before "
         "anything that could prime it)*",
         "  a) I intended to buy it, soon",
         "  b) I intended to buy it, but at some later point or occasion",
         "  c) I was saving it to look at again, without a plan to buy",
         "  d) I don't remember",
         "",
         "**S2.** Since saving it, how many times have you opened your saved list? "
         "*(0 / 1–2 / 3–5 / more than 5 / I can't find my saved list)*",
         "  > The last option is not a throwaway. Stage A is under-detected in the "
         "corpus by construction; this item is the one place it can be measured "
         "directly rather than inferred.",
         "",
         "## Main items",
         "",
         "**Q1.** Thinking of that item — what stopped you? *(select up to 2)*",
         ""]
    for r in d["opp"][:9]:
        spec = cb.codes.get(r["code"], {})
        L.append(f"  - {spec.get('question') or spec.get('name')}  "
                 f"_[{_fw(r['code'])} · {r['n']} records in the corpus]_")
    L += ["  - Something else — please say what",
          "  - Nothing stopped me; I just haven't got round to it",
          "",
          "  > The last two options carry weight. A forced-choice list of the corpus's "
          "own codes will reproduce the corpus's own ranking, which measures the "
          "instrument rather than the population. The residual share here is the "
          "check on that.",
          "",
          "**Q2.** How close were you to buying it? *(1 = just looking, 5 = about to pay)*",
          "",
          "**Q3.** Did you do anything to try to resolve it — search elsewhere, ask "
          "someone, check reviews, measure a garment you own? *(yes / no)*  ",
          "  **Q3a.** If yes: what did you do? *(free text)*",
          "  > Workarounds are the strongest evidence in the corpus, because effort "
          "proves an unmet need without the person being asked. Measuring it here lets "
          "the corpus's workaround rates be checked against a population that did not "
          "self-select into posting.",
          "",
          "**Q4.** Did you end up buying it, or something like it, anywhere? "
          "*(bought it here / bought elsewhere / bought something similar / no)*",
          "",
          "**Q5.** What would have had to be true for you to buy it that day? "
          "*(free text)*",
          "",
          "## Items testing specific hypotheses", ""]
    for h in d["hyps"][:5]:
        L += [f"**{h['hypothesis_id']}** — {h['statement'].split(chr(10))[0]}",
              f"  - Ask: an agree/disagree item stating the MECHANISM, not the outcome. "
              f"Disagreement is the informative answer.",
              f"  - Kill condition: {h['falsifier']}",
              ""]
    L += ["## Analysis plan, fixed before fielding",
          "",
          "- Report every result by the S1 segment. A pooled result mixes people with no "
          "purchase intent into a conversion question.",
          "- **Pre-register the comparison:** the corpus's ranked barriers are listed in "
          "Q1 in corpus order. If the survey's order differs materially, the corpus's "
          "ranking is a ranking of *discussion*, not of incidence — which is what it has "
          "always claimed to be, and this is how that claim gets tested.",
          "- Minimum n for a reported cell: 30, the same floor the corpus analysis uses.",
          ]
    return "\n".join(L) + "\n"


# ---------------------------------------------------- problem-framing canvas
def canvas(con, d: dict, cb) -> str:
    seg, addr = d["seg"], d["addr"]
    top = d["opp"][0] if d["opp"] else None
    novel = [i for i in d["insights"] if i["novelty"]]
    L = ["# Problem-framing canvas",
         f"_Generated {date.today().isoformat()} from the analysis tables. "
         "Every figure is a share of DISCUSSION, never a drop-off or conversion rate._",
         "",
         "## 1 · Who",
         ""]
    if seg:
        L += [f"**({seg['segment_id']}) {seg['segment_name']}** — {seg['n']} records, "
              f"{seg['share']:.1%} of the addressable population.",
              "", f"> {seg['rationale']}", ""]
    L += ["**Explicitly not this problem:**", "",
          f"- {addr['collectors']['n']} records ({addr['collectors']['share_of_corpus']:.1%}) are "
          "people saving as a taste archive. Converting them is not a goal; it would be "
          "optimising against the user.",
          f"- {addr['c9_no_live_intent']['n']} records "
          f"({addr['c9_no_live_intent']['share_of_corpus']:.1%}) show no live purchase intent at "
          "any point.",
          "",
          f"Both were counted before being removed, which is why the addressable "
          f"population is {addr['addressable']['n']} and not "
          f"{addr['corpus']['n']}.",
          "",
          "## 2 · What is in the way", ""]
    for r in d["opp"][:5]:
        spec = cb.codes.get(r["code"], {})
        L.append(f"**{r['rank']}. {_fw(r['code'])} — {spec.get('name','')}** · n={r['n']} · "
                 f"score {r['score']:.2f} · solvable without money: "
                 f"{SOLVABLE_LABEL.get(spec.get('solvable_without_money'), '?')}")
        L.append(f"   {spec.get('question','')}")
    L += ["", "## 3 · How confident, and how would we know we are wrong", ""]
    sens = list(con.execute("SELECT * FROM analysis_weight_sensitivity"
                            " ORDER BY top_share DESC LIMIT 2"))
    if sens and top:
        L += [f"- The top-ranked opportunity holds first place in "
              f"**{sens[0]['top_share']:.1%}** of 1,000 weightings perturbed ±30%. "
              + ("The ranking is robust to reasonable disagreement about the weights."
                 if sens[0]["top_share"] >= 0.75 else
                 "The top two cannot be separated on this evidence; the interviews are "
                 "the tiebreak, not a formality."),
              ]
    for iv in con.execute("SELECT * FROM analysis_stage_inversion"
                          " WHERE inversion_factor IS NOT NULL ORDER BY inversion_factor"):
        L.append(f"- Stage {iv['stage']} would have to be under-reported by "
                 f"**{iv['inversion_factor']:.1f}×** to overtake stage {iv['leader']}."
                 + ("  **That is plausible for a silent barrier — treat the stage "
                    "ranking as fragile.**" if iv["fragile"] else ""))
    L += ["- Known measurement failures, carried forward rather than restated as "
          "passing: per-code agreement with a human coder clears its threshold for only "
          "2 of 5 measurable codes; relevance recall is an estimate of ~79% against an "
          "85% threshold; C10 is unreliable at κ 0.10.",
          "",
          "## 4 · What we would learn that we do not know", ""]
    for h in d["hyps"][:4]:
        L.append(f"- **{h['hypothesis_id']}** ({h['confidence']} confidence): "
                 f"{h['falsifier']}")
    L += ["", "## 5 · Constraints that shape any answer", "",
          "- **No monetary incentives.** Discounts, coupons and cashback are out of "
          "scope, which matters most for the price/value barrier: it must resolve into "
          "transparency, anchoring or timing or not at all.",
          "- **No internal analytics.** Public feedback is a proxy for the funnel and "
          "never a substitute. Nothing here is a drop-off rate.",
          "- **Only ~36% of the corpus is Myntra-specific**, so platform-mechanical "
          "claims are ranked on their Myntra-specific counts.",
          ""]
    if novel:
        L += ["## 6 · What the corpus said that the framework did not predict", ""]
        for i in novel:
            L += [f"- {i['statement']}", f"  _{i['so_what']}_"]
    else:
        L += ["## 6 · Novelty", "",
              "No insight cleared the novelty filter against the 28 pre-registered "
              "hypotheses. Reported as a result rather than manufactured: the corpus "
              "largely confirmed existing priors.", ""]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DIR))
    a = ap.parse_args()

    con = dbm.connect(read_only=True)
    cb = cbm.load()
    d = load(con)
    if not d["hyps"]:
        print("no hypotheses — run hypotheses.py first")
        return 1

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for name, text in (("interview_guide.md", interview_guide(con, d, cb)),
                       ("survey_instrument.md", survey(con, d, cb)),
                       ("problem_framing_canvas.md", canvas(con, d, cb))):
        (out / name).write_text(text)
        print(f"  {(out / name).relative_to(ROOT)}  {len(text):,} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
