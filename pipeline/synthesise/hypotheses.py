"""FR-3.2 / task 3.2 — hypotheses with falsifiers.

An insight says what the corpus contains. A hypothesis says why, and a causal
claim is worth nothing without the conditions that would kill it. AC-7 is the
whole point of this file: every hypothesis carries **what would disprove it**
and **what already argues against it**.

WHAT THE MODEL WRITES, AND WHAT IT IS NOT ALLOWED TO WRITE
----------------------------------------------------------
The model supplies the parts that are genuinely judgement — the causal claim,
the mechanism, the falsifier, the reading of the counter-evidence. It does NOT
supply the supporting count, the verbatims, or the source diversity. Those are
COMPUTED from the codes it names.

That split is deliberate. Asking a model for `supporting_n` invites a plausible
number; deriving it from the classifications makes it a fact, and a hypothesis
whose evidence turns out to be thin then fails visibly rather than being
narrated as strong. The same logic makes verbatims record ids drawn from rows
with `span_verified = 1` — a quote that is not an exact substring of the record
is not evidence (T-6) and never reaches the page.

CONTRADICTING EVIDENCE IS RETRIEVED BEFORE IT IS ASKED FOR
-----------------------------------------------------------
`counter_signals()` computes the machine-findable objections for each code —
anti-correlated partners, single-source concentration, low classifier
confidence, known low agreement with the human coder — and puts them in the
prompt. A model asked "what contradicts this?" with no counter-evidence in
front of it writes a polite hedge. Given the actual objections, it has to
engage with them. "None found" stays a permitted answer (S3-INV-3), but it now
means something.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import codebook as cbm, db as dbm, env as envm, runs as rmod  # noqa: E402
from pipeline.synthesise import insights as ins, packet as pk  # noqa: E402

PROMPT_VERSION = "hypotheses_v1"
N_TARGET = 8
N_VERBATIM = 4

# Measured at the P2 gate. Kappa is only reported where gold n >= 5; the rest
# are "no information", not "no agreement" (DECISIONS.md).
GOLD_KAPPA = {"C1": 0.66, "C6": 0.64, "C3": 0.52, "C2": 0.43, "C10": 0.10}

SYSTEM = """You are writing the hypothesis section of a discovery study into why people do
not buy items they saved to a wishlist on Indian online fashion platforms.

A HYPOTHESIS IS A CAUSAL CLAIM WITH A KILL CONDITION. Not a summary, not a
recommendation. Its form is: because <mechanism>, <population> does <behaviour>,
which is why <observed pattern in the corpus> appears.

Every hypothesis you write must carry:

  statement    the causal claim, in one or two sentences.
  mechanism    why the cause produces the effect. If you cannot state the
               mechanism, you have a correlation, not a hypothesis.
  codes        the codebook codes whose records are the evidence. Everything
               quantitative — how many records, how many sources, which
               verbatims — is COMPUTED from this list, not written by you.
  confidence   high | medium | low. Earn it. Low is a legitimate answer and a
               hypothesis resting on a code with poor human agreement, one
               source, or n below 30 cannot be high.
  contradicting  what argues AGAINST this, engaging with the counter-signals
               supplied below. "None found" is permitted but only if you have
               looked at them and none apply — say which you checked.
  falsifier    THE MOST IMPORTANT FIELD. A specific observation that would kill
               the hypothesis, stated so a person planning five user interviews
               or a survey could actually run it. It must be capable of coming
               out either way.

               A good falsifier: "In interviews, if fewer than 2 of 6
               participants who abandoned over fit can name a specific size
               question they could not answer, the mechanism is wrong — the
               doubt is about the garment, not about the size chart."
               A bad falsifier: "If users do not care about fit." — untestable,
               and no interview produces that sentence.

HARD RULES
1. Shares are shares of DISCUSSION. Never a drop-off, conversion or user rate.
2. No monetary remedies exist for this product. Price findings must resolve
   into transparency, anchoring or timing, never into a discount.
3. Do not write a number that is not in the evidence packet.
4. Where a hypothesis rests on a code with known measurement problems, say so
   inside the hypothesis, not afterwards.
5. Cover different mechanisms. Eight restatements of the leading code would be
   a failed pass. At least one hypothesis should be one the corpus can only
   weakly support, and should say so.

Return strict JSON."""

SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "statement": {"type": "string"},
                "mechanism": {"type": "string"},
                "codes": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "contradicting": {"type": "string"},
                "falsifier": {"type": "string"},
            },
            "required": ["statement", "mechanism", "codes", "confidence",
                         "contradicting", "falsifier"],
            "additionalProperties": False}},
    },
    "required": ["hypotheses"], "additionalProperties": False,
}


def counter_signals(con) -> str:
    """The machine-findable objections, per code, handed over before they are
    asked for. This is the same idea as the chatbot's disconfirming-evidence
    channel (arch §8.4, Channel 3): retrieve AGAINST the emerging answer."""
    cb = cbm.load()
    lines = ["### COUNTER-SIGNALS — the objections already in the data",
             "_Engage with these in `contradicting`. Ignoring one is visible._"]
    for r in con.execute(
            "SELECT code, n, share, n_sources, mean_confidence FROM analysis_code_prevalence"
            " WHERE n >= 15 ORDER BY n DESC"):
        code, bits = r["code"], []
        if r["n_sources"] and r["n_sources"] <= 2:
            bits.append(f"only {r['n_sources']} of 4 sources carry it — may be an artefact "
                        "of who posts where")
        if r["mean_confidence"] and r["mean_confidence"] < 0.60:
            bits.append(f"mean classifier confidence {r['mean_confidence']:.2f} — the "
                        "classifier itself is unsure")
        if code in GOLD_KAPPA and GOLD_KAPPA[code] < 0.60:
            bits.append(f"human agreement kappa {GOLD_KAPPA[code]:.2f}, below the 0.60 "
                        "threshold — the code is not reliably applied")
        if r["n"] < 30:
            bits.append(f"n={r['n']} is below the floor for a ranked claim")
        anti = list(con.execute(
            "SELECT code_a, code_b, lift, n_joint FROM analysis_cooccurrence"
            " WHERE (code_a = ? OR code_b = ?) AND min_support_met = 1 AND lift < 0.75"
            " ORDER BY lift ASC LIMIT 2", (code, code)))
        for a in anti:
            other = a["code_b"] if a["code_a"] == code else a["code_a"]
            bits.append(f"ANTI-correlated with {other} (lift {a['lift']:.2f}, "
                        f"n_joint={a['n_joint']}) — any claim that these are one problem "
                        "is contradicted")
        src = con.execute(
            "SELECT source, share, n FROM analysis_source_code WHERE code = ?"
            " ORDER BY share DESC LIMIT 1", (code,)).fetchone()
        pooled = r["share"]
        if src and pooled and src["share"] > 2.0 * pooled:
            bits.append(f"concentrated in `{src['source']}` at {src['share']:.1%} vs "
                        f"{pooled:.1%} corpus-wide — source composition may be driving it")
        if bits:
            lines.append(f"{code} ({cb.codes.get(code, {}).get('name', '')}): "
                         + "; ".join(bits))
    return "\n".join(lines) + "\n"


def evidence_for(con, codes: list[str]) -> dict:
    """Supporting count, source diversity and verbatim ids — COMPUTED.

    Verbatims are drawn only from rows with `span_verified = 1` and are spread
    across distinct authors and sources, because four quotes from one person is
    one data point wearing four hats (EC-COL-9).
    """
    codes = [c for c in codes if c]
    if not codes:
        return {"supporting_n": 0, "source_diversity": 0, "verbatim_ids": []}
    ph = ",".join("?" * len(codes))
    rows = [dict(r) for r in con.execute(f"""
        SELECT cl.record_id, cl.code, cl.confidence, cl.evidence_span,
               rec.source, rec.author_hash
        FROM classifications cl
        JOIN records rec ON rec.record_id = cl.record_id
        JOIN relevance v ON v.record_id = cl.record_id AND v.is_relevant = 1
        WHERE cl.code IN ({ph}) AND cl.span_verified = 1
          AND rec.text_available = 1
          AND NOT EXISTS (SELECT 1 FROM exclusions e WHERE e.record_id = rec.record_id)
        ORDER BY cl.confidence DESC""", codes)]
    ids = {r["record_id"] for r in rows}
    picked, seen_author, seen_source = [], set(), set()
    for r in rows:                                   # first pass: spread the sources
        if len(picked) >= N_VERBATIM:
            break
        if r["author_hash"] in seen_author or r["source"] in seen_source:
            continue
        picked.append(r["record_id"]); seen_author.add(r["author_hash"])
        seen_source.add(r["source"])
    for r in rows:                                   # then top up by confidence
        if len(picked) >= N_VERBATIM:
            break
        if r["record_id"] in picked or r["author_hash"] in seen_author:
            continue
        picked.append(r["record_id"]); seen_author.add(r["author_hash"])
    return {"supporting_n": len(ids),
            "source_diversity": len({r["source"] for r in rows}),
            "verbatim_ids": picked}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5")
    ap.add_argument("--n", type=int, default=N_TARGET)
    a = ap.parse_args()

    con = dbm.connect()
    cb = cbm.load()
    packet = pk.build(con) + "\n" + counter_signals(con)
    known = set(cb.codes)

    from openai import OpenAI
    client = OpenAI(api_key=envm.load()["OPENAI_API_KEY"], timeout=300.0)

    with rmod.Run(con, "hypotheses", model=a.model, prompt_version=PROMPT_VERSION,
                  codebook_version=cb.version_string, n_requested=a.n) as run:
        run.n_input = a.n
        r = client.responses.create(
            model=a.model, instructions=SYSTEM,
            input=(f"{packet}\n\nWrite {a.n} hypotheses. Every one needs a falsifier a "
                   "person could run in five user interviews or a short survey."),
            reasoning={"effort": "medium"},
            text={"format": {"type": "json_schema", "name": "hypotheses",
                             "schema": SCHEMA, "strict": True}})
        run.add_usage(input_tokens=r.usage.input_tokens, output_tokens=r.usage.output_tokens)
        items = json.loads(r.output_text)["hypotheses"]

        con.execute("DELETE FROM hypotheses")
        kept, rejected = [], []
        for i, h in enumerate(items, 1):
            reasons = []
            bad_codes = [c for c in h["codes"] if c not in known]
            if bad_codes:
                reasons.append(f"unknown codes {bad_codes}")
            if not h["falsifier"].strip():
                reasons.append("empty falsifier (S3-INV-2 / AC-7)")
            if not h["contradicting"].strip():
                reasons.append("empty contradicting evidence (S3-INV-3)")
            m = ins.FUNNEL_LANGUAGE.search(h["statement"] + " " + h["mechanism"])
            if m:
                reasons.append(f"states a share as a funnel measure: {m.group(0)!r}")
            ev = evidence_for(con, h["codes"])
            if reasons:
                rejected.append({**h, "_reasons": reasons})
                continue
            hid = f"HYP-{len(kept) + 1:02d}"
            kept.append({**h, **ev, "hypothesis_id": hid})
            con.execute(
                "INSERT INTO hypotheses (hypothesis_id, statement, codes, supporting_n,"
                " verbatim_ids, source_diversity, confidence, contradicting, falsifier,"
                " run_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (hid, h["statement"] + "\n\nMechanism: " + h["mechanism"],
                 json.dumps(h["codes"]), ev["supporting_n"],
                 json.dumps(ev["verbatim_ids"]), ev["source_diversity"],
                 h["confidence"], h["contradicting"], h["falsifier"], run.run_id))
        con.commit()
        run.n_output = len(kept)

        print(f"generated {len(items)}  kept {len(kept)}  rejected {len(rejected)}"
              f"  cost ${run.cost_usd() or 0:.3f}\n")
        for h in kept:
            print(f"{h['hypothesis_id']} [{h['confidence']}] codes {h['codes']} "
                  f"n={h['supporting_n']} sources={h['source_diversity']}")
            print(f"  {h['statement']}")
            print(f"  MECHANISM   {h['mechanism']}")
            print(f"  AGAINST     {h['contradicting']}")
            print(f"  FALSIFIER   {h['falsifier']}\n")
        for h in rejected:
            print(f"REJECTED ({'; '.join(h['_reasons'])}): {h['statement'][:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
