"""LLM pass 0 — relevance (FR-2.1).

Runs only on prefilter survivors. Scored with the frontier model against a
written rubric whose hardest case (EC-REL-1: a past bad experience cited as
present hesitation) is over-sampled in the gold set and tested by S2-MET-8.

Output is deliberately terse. `reason` is capped at a short phrase because
output tokens are ~80% of the project's LLM bill (arch §9.2) and this pass
does not need to justify itself at length -- the classification pass does.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402

PROMPT_VERSION = "relevance_v1"
RUBRIC = (Path(__file__).resolve().parents[2] / "prompts" / "relevance_v1.md").read_text()

SCHEMA = {
    "type": "object",
    "properties": {
        "is_relevant": {"type": "boolean"},
        "reason": {"type": "string", "description": "at most 12 words"},
        "confidence": {"type": "number"},
        "secondhand": {"type": "boolean"},
        "myntra_specific": {"type": "boolean"},
    },
    "required": ["is_relevant", "reason", "confidence", "secondhand", "myntra_specific"],
    "additionalProperties": False,
}


def classify_one(client, model: str, rec: dict) -> tuple[dict, dict]:
    ctx = f"[context: {rec['thread_context']}]\n" if rec.get("thread_context") else ""
    r = client.responses.create(
        model=model,
        instructions=RUBRIC,
        input=f"{ctx}[source: {rec['source']}]\n\n{rec['text_raw'][:4000]}",
        reasoning={"effort": "low"},
        text={"format": {"type": "json_schema", "name": "relevance",
                         "schema": SCHEMA, "strict": True}},
    )
    return json.loads(r.output_text), {
        "in": r.usage.input_tokens,
        "out": r.usage.output_tokens,
        "cached": getattr(getattr(r.usage, "input_tokens_details", None), "cached_tokens", 0) or 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0,
                    help="stratified sample per source (0 = all prefilter survivors)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    v = envm.load()
    from openai import OpenAI
    client = OpenAI(api_key=v["OPENAI_API_KEY"], timeout=180.0)
    model = args.model or rmod.CLASSIFIER_MODEL

    con = dbm.connect()
    if args.sample:
        # Stratified across sources: a pilot drawn mostly from one source
        # measures the wrong thing (arch §5.2).
        rows = []
        for (src,) in con.execute("SELECT DISTINCT source FROM retained"):
            rows += [dict(r) for r in con.execute("""
                SELECT r.record_id, r.source, r.text_raw, r.thread_context
                FROM retained r JOIN prefilter p ON p.record_id=r.record_id
                WHERE p.passed=1 AND r.source=?
                ORDER BY p.embed_score DESC LIMIT ?""", (src, args.sample))]
    else:
        rows = [dict(r) for r in con.execute("""
            SELECT r.record_id, r.source, r.text_raw, r.thread_context
            FROM retained r JOIN prefilter p ON p.record_id=r.record_id
            WHERE p.passed=1""")]

    done = {r[0] for r in con.execute("SELECT record_id FROM relevance")}
    rows = [r for r in rows if r["record_id"] not in done]
    print(f"scoring {len(rows)} records with {model}  ({len(done)} already done)\n")
    if not rows:
        return 0

    with rmod.Run(con, "relevance", model=model, prompt_version=PROMPT_VERSION) as run:
        run.n_input = len(rows)
        ok = err = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(classify_one, client, model, r): r for r in rows}
            for i, fut in enumerate(as_completed(futs), 1):
                rec = futs[fut]
                try:
                    out, usage = fut.result()
                except Exception as e:                          # noqa: BLE001
                    # EC-CLS-14: quarantined, never dropped silently.
                    con.execute(
                        "INSERT OR IGNORE INTO quarantine (record_id, stage, error, run_id)"
                        " VALUES (?,?,?,?)",
                        (rec["record_id"], "relevance", f"{type(e).__name__}: {e}"[:400], run.run_id))
                    err += 1
                    continue
                run.add_usage(input_tokens=usage["in"], output_tokens=usage["out"],
                              cached_tokens=usage["cached"])
                con.execute(
                    "INSERT OR REPLACE INTO relevance (record_id, is_relevant, reason,"
                    " confidence, secondhand, myntra_specific, run_id) VALUES (?,?,?,?,?,?,?)",
                    (rec["record_id"], int(out["is_relevant"]), out["reason"][:200],
                     float(out["confidence"]), int(out["secondhand"]),
                     int(out["myntra_specific"]), run.run_id))
                ok += 1
                if i % 100 == 0:
                    con.commit()
                    print(f"  {i}/{len(rows)}  ok={ok} err={err}  "
                          f"${run.cost_usd() or 0:.3f}", flush=True)
        con.commit()
        run.n_output = ok
        print(f"\n  scored {ok}, quarantined {err}, cost ${run.cost_usd() or 0:.3f}")

    print(f"\n  {'source':<10} {'scored':>8} {'relevant':>9} {'YIELD':>7}")
    for s, n, rel in con.execute("""
        SELECT r.source, count(*), sum(v.is_relevant)
        FROM relevance v JOIN records r ON r.record_id=v.record_id
        GROUP BY r.source ORDER BY count(*) DESC"""):
        print(f"  {s:<10} {n:>8,} {rel:>9,} {rel / n:>6.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
