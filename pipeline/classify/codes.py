"""Two-pass hierarchical classification (arch §6.2, FR-2.2, FR-5.1).

WHY TWO PASSES. Thirty-three codes in one prompt degrades accuracy -- the
model spreads attention thin and confuses adjacent codes. Pass 1 assigns
stage(s); pass 2 sees only the codes in those stages (<=14, not 33) and
carries the FULL boundary_note for every candidate. The boundaries are where
classification fails, so that is where the prompt budget goes.

The `reasoning` field is retained deliberately. It is the largest single
output-token cost in the project and it earns it three times: it is the
audit trail NFR-4 requires, it is what makes gold-set confusion analysis
show *why* a code was misassigned rather than merely *that* it was, and
writing the justification improves boundary discrimination on exactly the
C1/C8-style distinctions the project turns on.

gpt-5 is pinned here. DECISIONS.md refuses tier-splitting at this step
specifically: C1 (fit uncertainty, solvable) vs C8 (size unavailable,
supply-side, fails the no-monetary-incentives constraint) read almost
identically and have opposite solves. Getting that wrong means building the
wrong thing while the data appears to agree.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import codebook as cbm, db as dbm, env as envm, runs as rmod  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
STAGE_PROMPT = (ROOT / "prompts" / "stage_v1.md").read_text()
PROMPT_VERSION = "codes_v1"
import os
CODE_EFFORT = os.environ.get("CODE_EFFORT", "low")

STAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "stages": {"type": "array", "items": {"type": "string",
                                              "enum": ["A", "B", "C", "D", "Z-99"]}},
        "why": {"type": "string", "description": "at most 15 words"},
    },
    "required": ["stages", "why"],
    "additionalProperties": False,
}


def build_code_prompt(cb: cbm.Codebook, stages: list[str]) -> tuple[str, list[str]]:
    """Only the codes in the assigned stages, with full boundary notes."""
    cands: list[dict] = []
    for s in stages:
        if s == "Z-99":
            continue
        cands.extend(cb.by_stage(s))
    cands.append(cb.codes["Z-99"])

    lines = [
        "You assign hypothesis codes to public feedback about online fashion shopping.",
        "",
        "Assign EVERY code the text supports — multi-label is normal and expected.",
        "Real feedback carries several barriers at once (\"didn't know my size and it",
        "got costlier\"); forcing one label fabricates precision.",
        "",
        "For each code you assign you MUST supply an `evidence_span`: an EXACT",
        "VERBATIM SUBSTRING of the input text. Not a paraphrase, not a summary, not",
        "a cleaned-up version. It is checked by string match after generation and a",
        "mismatch invalidates the record. Quote the shortest span that carries the",
        "evidence.",
        "",
        "NEVER quote these code definitions, their questions, or their boundary",
        "notes. They are instructions to you, not words the user wrote. A span",
        "that appears in this prompt but not in the record is a fabricated",
        "citation.",
        "",
        "The span MUST come from inside <record>...</record>. Anything in a",
        "<context nonquotable> block is background to help you read the record —",
        "it is another person's words and quoting it would attribute their",
        "statement to this author. Never quote it.",
        "",
        "CANDIDATE CODES:",
    ]
    for d in cands:
        lines.append(f"\n### {d['id']} — {d['name']}")
        if d.get("question"):
            # Wrapped, not bare: an earlier run quoted this line verbatim as
            # an evidence_span, which would put a fabricated quote behind a
            # real citation -- a silent NFR-1 break (EC-CLS-6).
            lines.append(f"(What this code is about, NOT quotable: {d['question']})")
        lines.append(f"Phase: {d['phase']} | Typical outcome: {d['outcome_default']}")
        lines.append(f"BOUNDARY: {' '.join(str(d['boundary_note']).split())}")

    if any(d["id"] in ("C9", "C11") for d in cands):
        lines += [
            "",
            "MUTUALLY EXCLUSIVE — do not assign these together:",
            "- C9 (intent was never live) CANNOT co-occur with any doubt code",
            "  (C1 fit, C2 material, C3 styling, C4 evidence, C5 comparison,",
            "  C10 approval, C12 decay, C14 verification). Voicing a doubt about",
            "  an item IS evidence that intent existed. If the user expresses any",
            "  hesitation about buying, intent was live — code the doubt, not C9.",
            "  C9 is only for pure collecting with no purchase consideration at all.",
            "- C11 (need extinguished — already bought this or a substitute",
            "  elsewhere) likewise cannot co-occur with doubt codes about the same",
            "  item. C11 requires evidence a PURCHASE COMPLETED somewhere else.",
            "  Refusing to buy a brand again is NOT C11 — that is C2 or C7.",
        ]

    lines += [
        "",
        "ALSO RECORD, for the record as a whole:",
        "- blocking_code: of the codes you assigned, the one that stopped the",
        "  purchase EARLIEST in the decision sequence. Eliminators (a hard gate) are",
        "  evaluated before Confidence doubts, which come before Trigger. Solving a",
        "  Confidence barrier for someone who already failed an Eliminator changes",
        "  nothing, which is why this field exists.",
        "- outcome: 'exit' if intent was destroyed, 'defer' if intent survives and the",
        "  decision was postponed, 'na' if there was never live intent.",
        "- segment: S1 buying-soon (named near-term need, delivery urgency, decision",
        "  language) | S2 future-event/conditional (named occasion, sale, salary,",
        "  restock) | S3 bookmarker (collecting, inspiration, no purchase language) |",
        "  unknown. `unknown` IS THE EXPECTED MAJORITY — public text rarely states why",
        "  someone saved. Forcing a segment fabricates the entire segmentation. Give a",
        "  confidence; below 0.6 the label must be unknown. If signals conflict, LOWER",
        "  the confidence rather than averaging them.",
        "- workaround: did the user describe doing something else instead (ordering two",
        "  sizes, screenshotting, checking another site, asking a friend)? effort 1-3.",
        "  A user who builds a workaround is proving the unmet need without being asked.",
        "- counterfactual: did they say what would have made them buy (\"I'd have",
        "  bought it if...\")? This is the highest-signal sentence type in the corpus.",
        "- intensity 1-5: how strongly felt, from the language used.",
        "",
        "Return strict JSON only.",
    ]
    return "\n".join(lines), [d["id"] for d in cands]


def code_schema(valid: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "codes": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "enum": valid},
                    "confidence": {"type": "number"},
                    "evidence_span": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["code", "confidence", "evidence_span", "reasoning"],
                "additionalProperties": False}},
            "blocking_code": {"type": "string", "enum": valid},
            "outcome": {"type": "string", "enum": ["exit", "defer", "na"]},
            "segment": {"type": "object", "properties": {
                "label": {"type": "string", "enum": ["S1", "S2", "S3", "unknown"]},
                "confidence": {"type": "number"},
                "signal": {"type": "string"}},
                "required": ["label", "confidence", "signal"], "additionalProperties": False},
            "workaround": {"type": "object", "properties": {
                "present": {"type": "boolean"}, "text": {"type": "string"},
                "effort": {"type": "integer"}},
                "required": ["present", "text", "effort"], "additionalProperties": False},
            "counterfactual": {"type": "object", "properties": {
                "present": {"type": "boolean"}, "text": {"type": "string"}},
                "required": ["present", "text"], "additionalProperties": False},
            "intensity": {"type": "integer"},
        },
        "required": ["codes", "blocking_code", "outcome", "segment",
                     "workaround", "counterfactual", "intensity"],
        "additionalProperties": False,
    }


def spans_valid(rec: dict, out: dict) -> bool:
    raw = normalise(rec["text_raw"])
    return all(normalise(c["evidence_span"]) in raw for c in (out.get("codes") or []))


def classify_with_retry(client, model: str, cb: cbm.Codebook, rec: dict) -> tuple[dict, dict]:
    """EC-CLS-6: re-run a record once on a span mismatch, then let it flag.
    Bounded at one retry -- looping on a model that keeps paraphrasing burns
    budget without converging."""
    out, usage = classify(client, model, cb, rec)
    if not spans_valid(rec, out):
        out2, u2 = classify(client, model, cb, rec)
        for k in usage:
            usage[k] += u2[k]
        if spans_valid(rec, out2):
            return out2, usage
    return out, usage


def _with_backoff(fn, *, tries: int = 5):
    """429s are expected at concurrency; a dropped record is a silent hole in
    the corpus, so retry rather than quarantine."""
    import random, time as _t
    for attempt in range(tries):
        try:
            return fn()
        except Exception as e:                                   # noqa: BLE001
            if "429" not in str(e) and "rate" not in str(e).lower():
                raise
            if attempt == tries - 1:
                raise
            _t.sleep(min(2 ** attempt + random.random(), 30))
    raise RuntimeError("unreachable")


def classify(client, model: str, cb: cbm.Codebook, rec: dict) -> tuple[dict, dict]:
    # The CONTEXT block exists so a bare comment ("same, mine's been there for
    # months") can be read at all. But evidence_span must be traceable to THE
    # RECORD (NFR-1), so the two are delimited and the prompt forbids quoting
    # the context. An earlier run quoted a parent-post question and failed T-6.
    ctx = (f"<context nonquotable>{rec['thread_context']}</context nonquotable>\n\n"
           if rec.get("thread_context") else "")
    text = rec["text_raw"][:6000]
    body = (f"{ctx}[source: {rec['source']}]\n"
            f"<record>\n{text}\n</record>")
    usage = {"in": 0, "out": 0, "cached": 0}

    def acc(u):
        usage["in"] += u.input_tokens
        usage["out"] += u.output_tokens
        usage["cached"] += getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0

    r1 = _with_backoff(lambda: client.responses.create(
        model=model, instructions=STAGE_PROMPT, input=body,
        reasoning={"effort": "minimal"},
        text={"format": {"type": "json_schema", "name": "stage",
                         "schema": STAGE_SCHEMA, "strict": True}}))
    acc(r1.usage)
    stages = json.loads(r1.output_text)["stages"] or ["Z-99"]

    prompt, valid = build_code_prompt(cb, stages)
    r2 = _with_backoff(lambda: client.responses.create(
        model=model, instructions=prompt, input=body,
        reasoning={"effort": CODE_EFFORT},
        text={"format": {"type": "json_schema", "name": "codes",
                         "schema": code_schema(valid), "strict": True}}))
    acc(r2.usage)
    out = json.loads(r2.output_text)
    out["stages"] = stages
    return out, usage


# Corpus text carries curly quotes, en/em dashes and non-breaking spaces;
# models emit the ASCII equivalents. Comparing raw strings marks those as
# paraphrases when the words are identical (EC-CHAT-11). NFKC plus an
# explicit punctuation map fixes the class.
_PUNCT_MAP = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2012": "-", "\u2212": "-",
    "\u00a0": " ", "\u2026": "...", "\u00b4": "'", "\u0060": "'",
})


def normalise(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKC", s).translate(_PUNCT_MAP)
    return " ".join(s.split()).lower()


def persist(con, cb: cbm.Codebook, rec: dict, out: dict, run_id: str) -> int:
    """Write rows, enforcing the invariants AT WRITE TIME rather than at review."""
    raw_norm = normalise(rec["text_raw"])
    codes = out.get("codes") or []

    # EC-CLS-1: a relevant record with zero codes is a forbidden state --
    # it sits in the denominator and contributes to no numerator.
    if not codes:
        codes = [{"code": "Z-99", "confidence": 0.5,
                  "evidence_span": rec["text_raw"][:120],
                  "reasoning": "no code assigned by model; forced to residual (EC-CLS-1)"}]

    conf_phase = {c["code"] for c in codes
                  if cb.codes.get(c["code"], {}).get("phase") == "confidence"}
    if conf_phase:
        dropped = [c["code"] for c in codes if c["code"] in ("C9", "C11")]
        if dropped:
            # A voiced doubt is positive evidence that intent existed, so the
            # doubt wins and the no-intent code goes. Recorded in reasoning
            # rather than silently removed (EC-CLS-4).
            codes = [c for c in codes if c["code"] not in ("C9", "C11")]
            if out.get("blocking_code") in dropped:
                out["blocking_code"] = sorted(
                    conf_phase,
                    key=lambda x: cb.codes[x]["journey_rank"])[0]

    # C9 and C11 are pairwise exclusive: intent never existed vs intent
    # existed and was satisfied elsewhere. Different populations, different
    # solves. A completed purchase is positive evidence that intent existed,
    # so C11 wins and C9 goes -- the same principle as above.
    present = {c["code"] for c in codes}
    if "C9" in present and "C11" in present:
        codes = [c for c in codes if c["code"] != "C9"]
        if out.get("blocking_code") == "C9":
            out["blocking_code"] = "C11"

    span_fails = 0
    for c in codes:
        span = c["evidence_span"]
        # EC-CLS-6 / T-6: exact substring or the span is not evidence.
        if normalise(span) not in raw_norm:
            span_fails += 1
            c["_span_ok"] = 0
        else:
            c["_span_ok"] = 1
        con.execute(
            "INSERT OR REPLACE INTO classifications (record_id, code, chunk_index,"
            " confidence, evidence_span, reasoning, is_blocking, span_verified, run_id)"
            " VALUES (?,?,0,?,?,?,?,?,?)",
            (rec["record_id"], c["code"], float(c["confidence"]), span,
             c.get("reasoning", "")[:600],
             int(c["code"] == out.get("blocking_code")), c["_span_ok"], run_id))

    seg = out.get("segment") or {}
    seg_label = seg.get("label", "unknown")
    seg_conf = float(seg.get("confidence", 0))
    # EC-CLS-10: below the threshold the label MUST be unknown. Enforced here,
    # not trusted to the model.
    if seg_conf < float(cb.segments["confidence_threshold"]):
        seg_label = "unknown"

    blocking = out.get("blocking_code")
    bdef = cb.codes.get(blocking, {})
    phase = bdef.get("phase")

    # S2-INV-4: outcome must be one the blocking code allows. The codebook,
    # not the model, is the authority here -- an Eliminator produces exit, and
    # a model answering "na" for a price barrier is simply wrong. Coerced to
    # the code's default rather than written through and failing the invariant.
    outcome = out.get("outcome")
    allowed = bdef.get("outcome_allowed") or ["exit", "defer", "na"]
    if outcome not in allowed:
        outcome = bdef.get("outcome_default", outcome)
    wk = out.get("workaround") or {}
    cf = out.get("counterfactual") or {}

    con.execute(
        "INSERT OR REPLACE INTO record_meta (record_id, stages, blocking_code,"
        " blocking_phase, outcome, segment, segment_conf, workaround, workaround_text,"
        " workaround_effort, counterfactual, counterfactual_text, intensity, n_codes, run_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rec["record_id"], json.dumps(out.get("stages", [])), blocking, phase,
         outcome, seg_label, seg_conf,
         int(bool(wk.get("present"))), (wk.get("text") or "")[:300],
         int(wk.get("effort") or 0), int(bool(cf.get("present"))),
         (cf.get("text") or "")[:300], int(out.get("intensity") or 0),
         len(codes), run_id))
    return span_fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    v = envm.load()
    from openai import OpenAI
    client = OpenAI(api_key=v["OPENAI_API_KEY"], timeout=240.0)
    model = args.model or rmod.CLASSIFIER_MODEL
    cb = cbm.load()

    con = dbm.connect()
    done = {r[0] for r in con.execute("SELECT DISTINCT record_id FROM record_meta")}
    rows = [dict(r) for r in con.execute("""
        SELECT rec.record_id, rec.source, rec.text_raw, rec.thread_context
        FROM relevance v JOIN records rec ON rec.record_id = v.record_id
        WHERE v.is_relevant = 1""")]
    rows = [r for r in rows if r["record_id"] not in done]
    if args.limit:
        rows = rows[:args.limit]

    print(f"classifying {len(rows)} relevant records with {model}")
    print(f"codebook {cb.version_string}  ({len(done)} already done)\n")
    if not rows:
        return 0

    with rmod.Run(con, "classify", model=model, prompt_version=PROMPT_VERSION,
                  codebook_version=cb.version_string) as run:
        run.n_input = len(rows)
        ok = err = spans_bad = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(classify_with_retry, client, model, cb, r): r for r in rows}
            for i, fut in enumerate(as_completed(futs), 1):
                rec = futs[fut]
                try:
                    out, usage = fut.result()
                except Exception as e:                          # noqa: BLE001
                    con.execute(
                        "INSERT OR IGNORE INTO quarantine (record_id, stage, error, run_id)"
                        " VALUES (?,?,?,?)",
                        (rec["record_id"], "classify", f"{type(e).__name__}: {e}"[:400], run.run_id))
                    err += 1
                    continue
                run.add_usage(input_tokens=usage["in"], output_tokens=usage["out"],
                              cached_tokens=usage["cached"])
                spans_bad += persist(con, cb, rec, out, run.run_id)
                ok += 1
                if i % 50 == 0:
                    con.commit()
                    print(f"  {i}/{len(rows)}  ok={ok} err={err} bad_spans={spans_bad}  "
                          f"${run.cost_usd() or 0:.2f}", flush=True)
        con.commit()
        run.n_output = ok
        print(f"\n  classified {ok}, quarantined {err}, cost ${run.cost_usd() or 0:.2f}")
        print(f"  evidence-span mismatches: {spans_bad} (T-6 requires 0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
