"""FR-3.1 / task 3.1 — generate insights over the analysis tables.

An insight here is a QUANTIFIED STATEMENT WITH EVIDENCE: a claim that names its
number and names the row the number came from. Anything else is an opinion with
a citation attached.

THE GENERATION IS UNTRUSTED BY DESIGN
-------------------------------------
The model is the weakest link in a pipeline that is otherwise anchored at every
step, so nothing it returns is stored on its say-so. Each insight passes three
deterministic gates before it reaches the database:

  1. every `{table, key}` citation must RESOLVE to a row that exists
     (`citations.check`) — EC-INS-6 / S3-INV-1;
  2. every numeral in the statement must be supported by one of those rows
     (`verify.check_numerals`) — a citation proves the sentence points at a row,
     not that it reports what the row says;
  3. the statement must not render a share as a drop-off or conversion rate
     (`problemstatement.md` §8) — the corpus measures discussion, and the whole
     project's honesty rests on that distinction holding at the last step.

Rejections are counted, printed, and written into the run's params, never
silently dropped. A generation pass that produced twelve insights and kept five
is a different thing from one that produced five, and the gate report says
which happened.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402
from pipeline.synthesise import citations as ct, packet as pk, verify as vf  # noqa: E402

PROMPT_VERSION = "insights_v1"
N_TARGET = 14

# §8, enforced rather than requested. These phrasings turn a share of
# discussion into a funnel measurement, which is the single misreading this
# project is most likely to be criticised for and the easiest to prevent.
FUNNEL_LANGUAGE = re.compile(
    r"\b(drop[- ]?off|drop out|conversion rate|convert(?:s|ed)? at|abandon(?:ment)? rate|"
    r"of (?:all )?users (?:who|that)|of shoppers (?:who|that)|churn(?:ed)? at|"
    r"funnel (?:rate|loss)|purchase rate)\b", re.I)

SYSTEM = """You are a research analyst writing the findings section of a discovery study
into why people do not buy items they have saved to a wishlist on Indian online
fashion platforms.

Your evidence is the attached packet of materialised analysis tables. It is
everything you know. You have no access to the underlying records, to Myntra's
internal analytics, or to anything outside the packet.

WHAT AN INSIGHT IS
An insight is a quantified statement about the corpus that a sceptical reader
could check against a row. It has a number, a direction, and a consequence. It
is not a restatement of a table row, and it is not advice.

  Weak : "C2 is the most common barrier."            (restates one cell)
  Weak : "Myntra should add a fit finder."           (advice, not a finding)
  Good : "The two leading barriers are the same doubt at different distances:
          C1 and C2 co-occur at lift 2.4, and 61% of C2 is the sub-code about
          quality-for-the-price rather than about the photograph."

WHERE THE INTERESTING THINGS ARE
Prevalence tables are the least interesting part of the packet; the ranking is
already known. Look for structure:
  - co-occurrence lift: two codes that travel together are one problem;
  - the Track B clusters, which were named BLIND by a model that never saw the
    codebook. A cluster that spreads across many codes is a situation the
    codebook cuts through. A cluster that is mostly Z-99 is one it misses;
  - sub-codes, where a theme's headline number and what it is actually about
    can differ sharply;
  - workaround and counterfactual rates: effort spent proves an unmet need more
    strongly than complaint volume does;
  - source divergence: a code that lives on one platform may be an artefact of
    who posts there;
  - what is ABSENT. A code at n=0 across 1,018 records is a finding, and Stage A
    is under-detected by construction because forgetting produces no complaint.

RULES, ALL OF THEM HARD
1. CITE. Every insight names one or more rows as {"table": ..., "key": ...},
   using the `key` shown in the packet. An insight whose citation does not
   resolve is discarded.
2. NUMBERS COME FROM CITED ROWS. Every numeral you write must appear in a row
   you cite. Do not compute new ratios between tables, do not round loosely,
   do not estimate.
3. SHARES ARE SHARES OF DISCUSSION. Never write, or imply, that a share is a
   drop-off rate, a conversion rate, or a proportion of users. "24% of
   save-decision discussion" is correct; "24% of shoppers" is not.
4. NO MONETARY REMEDIES. The project forbids discounts, coupons and cashback.
   Price findings must be resolved into transparency, anchoring or timing.
5. STATE WEAKNESS IN THE SAME SENTENCE AS THE CLAIM. If a claim rests on n
   below 30, on one source, or on a code whose mean confidence is low, say so
   where the claim is, not in a footnote.
6. NO ADVICE. Findings only. What to build is a later decision by a person.

Return strict JSON."""

SCHEMA = {
    "type": "object",
    "properties": {
        "insights": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "statement": {"type": "string"},
                "so_what": {"type": "string"},
                "cites": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"table": {"type": "string"}, "key": {"type": "string"}},
                    "required": ["table", "key"], "additionalProperties": False}},
                "n": {"type": "integer"},
                "kind": {"type": "string", "enum": [
                    "prevalence", "structure", "segment", "method", "absence", "contradiction"]},
            },
            "required": ["statement", "so_what", "cites", "n", "kind"],
            "additionalProperties": False}},
    },
    "required": ["insights"], "additionalProperties": False,
}


def generate(client, model: str, packet: str, n: int) -> tuple[list[dict], object]:
    r = client.responses.create(
        model=model, instructions=SYSTEM,
        input=(f"{packet}\n\nWrite {n} insights. Spread them across the `kind` values — "
               "a set of fourteen prevalence restatements would be a failed pass. "
               "Include at least two that draw on the blind Track B clusters, and at "
               "least one about what the corpus CANNOT show."),
        reasoning={"effort": "medium"},
        text={"format": {"type": "json_schema", "name": "insights",
                         "schema": SCHEMA, "strict": True}})
    return json.loads(r.output_text)["insights"], r.usage


REPAIR = """Some insights were REJECTED by the deterministic checker. Each is shown with
the exact reason. The checker is not negotiable and will run again.

Repair them. For a citation error, find the row that actually holds the number
and cite THAT — the claim may well be true and pointing at the wrong row. For an
unsupported numeral, either cite the row holding it or remove the number. If an
insight cannot be repaired without inventing something, drop it and say nothing
in its place; a smaller honest set is the correct outcome.

Return only the repaired insights, in the same schema."""


def repair(client, model: str, packet: str, rejected: list[dict]) -> tuple[list[dict], object]:
    """AR-11-style bounded regeneration: ONE retry, then whatever survives is
    what ships. A rejection is usually a mis-citation of a true claim — the
    number exists, in a row the model did not name — and discarding those
    silently would make the checker look stricter than it is while quietly
    costing real findings. Never loops: one pass, then stop."""
    listing = "\n\n".join(
        f"REJECTED: {it['statement']}\n  cites: "
        + "; ".join(f"{c['table']}[{c['key']}]" for c in it.get("cites") or [])
        + "\n  reason: " + "; ".join(it["_reasons"])
        for it in rejected)
    r = client.responses.create(
        model=model, instructions=SYSTEM,
        input=f"{packet}\n\n{REPAIR}\n\n{listing}",
        reasoning={"effort": "medium"},
        text={"format": {"type": "json_schema", "name": "insights",
                         "schema": SCHEMA, "strict": True}})
    return json.loads(r.output_text)["insights"], r.usage


def validate(con, items: list[dict]) -> tuple[list[dict], list[dict]]:
    kept, rejected = [], []
    for i, it in enumerate(items, 1):
        rows, bad = ct.check(con, it.get("cites") or [])
        reasons = list(bad)
        if rows:
            nums = vf.check_numerals(it["statement"], rows)
            if nums:
                reasons.append("unsupported numerals: " + ", ".join(nums))
        m = FUNNEL_LANGUAGE.search(it["statement"] + " " + it.get("so_what", ""))
        if m:
            reasons.append(f"states a share as a funnel measure: {m.group(0)!r}")
        (rejected if reasons else kept).append({**it, "_rows": rows, "_reasons": reasons})
    return kept, rejected


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5")
    ap.add_argument("--n", type=int, default=N_TARGET)
    ap.add_argument("--dry-run", action="store_true", help="print the packet, make no call")
    ap.add_argument("--no-repair", action="store_true",
                    help="skip the single bounded repair pass over rejected insights")
    a = ap.parse_args()

    con = dbm.connect()
    packet = pk.build(con)
    if a.dry_run:
        print(packet)
        return 0

    from openai import OpenAI
    client = OpenAI(api_key=envm.load()["OPENAI_API_KEY"], timeout=300.0)

    with rmod.Run(con, "insights", model=a.model, prompt_version=PROMPT_VERSION,
                  n_requested=a.n) as run:
        run.n_input = a.n
        items, usage = generate(client, a.model, packet, a.n)
        run.add_usage(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
        kept, rejected = validate(con, items)
        n_first_pass, n_rejected_first = len(items), len(rejected)

        if rejected and not a.no_repair:
            fixed, usage2 = repair(client, a.model, packet, rejected)
            run.add_usage(input_tokens=usage2.input_tokens, output_tokens=usage2.output_tokens)
            kept2, rejected = validate(con, fixed)
            kept += kept2
            print(f"repair pass: {len(rejected)} still rejected, {len(kept2)} recovered")

        con.execute("DELETE FROM insights")
        for i, it in enumerate(kept, 1):
            con.execute(
                "INSERT INTO insights (insight_id, statement, so_what, kind, cites, n,"
                " novelty, run_id) VALUES (?,?,?,?,?,?,?,?)",
                (f"INS-{i:02d}", it["statement"], it["so_what"], it["kind"],
                 json.dumps(it["cites"]), it.get("n"), 0, run.run_id))
        con.commit()
        run.n_output = len(kept)

        print(f"generated {n_first_pass} ({n_rejected_first} rejected on the first pass)"
              f"  kept {len(kept)}  finally rejected {len(rejected)}"
              f"  cost ${run.cost_usd() or 0:.3f}\n")
        for i, it in enumerate(kept, 1):
            print(f"INS-{i:02d} [{it['kind']}] {it['statement']}")
            print(f"       so what: {it['so_what']}")
            print(f"       cites: " + "; ".join(f"{c['table']}[{c['key']}]" for c in it["cites"]))
            print()
        for it in rejected:
            print(f"REJECTED ({'; '.join(it['_reasons'])})\n  {it['statement'][:200]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
