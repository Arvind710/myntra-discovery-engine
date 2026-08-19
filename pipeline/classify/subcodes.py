"""Sub-code the leading Stage C themes against the updated framework.

Not a re-classification. The sub-theme assignment (C1..C8) already agrees
between the engine codebook and the framework, so this pass only asks the
finer question WITHIN a theme that already has evidence:

    C2 leads at 249 records. Knowing it is C2.1 fabric/drape rather than
    C2.5 authenticity is the difference between a swatch/zoom feature and a
    seller-verification feature. The headline number does not tell you which
    to build; the sub-code does.

Runs only on themes above the ranked-claim floor (n >= 30), because a
sub-split of a thin theme produces cells nobody can act on.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CROSSWALK = yaml.safe_load((ROOT / "codebook" / "crosswalk_v2.yaml").read_text())
PROMPT_VERSION = "subcodes_v1"


def theme_prompt(theme: str, subcodes: dict[str, str]) -> tuple[str, list[str]]:
    ids = list(subcodes) + ["unclear"]
    lines = [
        f"A record has already been identified as theme {theme} "
        f"({CROSSWALK['stage_c'][theme]['name']}).",
        "",
        "Assign the specific sub-code(s) that the text supports. Multi-label is",
        "allowed where the text genuinely carries more than one.",
        "",
        "SUB-CODES:",
    ]
    for sid, desc in subcodes.items():
        lines.append(f"  {sid} — {desc}")
    lines += [
        "  unclear — the record supports the theme but not any specific sub-code.",
        "",
        "Use `unclear` honestly. A forced sub-code is worse than an admitted one:",
        "the whole point of splitting the theme is to decide what to build, and a",
        "guess sends that decision the wrong way. If the text says only 'the",
        "quality was not what I expected', that is the theme without a sub-code.",
        "",
        "Return strict JSON only.",
    ]
    return "\n".join(lines), ids


def schema(ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "subcodes": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "subcode": {"type": "string", "enum": ids},
                    "confidence": {"type": "number"},
                },
                "required": ["subcode", "confidence"],
                "additionalProperties": False}},
        },
        "required": ["subcodes"],
        "additionalProperties": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--themes", nargs="*", default=["C2", "C3", "C1"])
    ap.add_argument("--model", default="gpt-5-mini")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    v = envm.load()
    from openai import OpenAI
    client = OpenAI(api_key=v["OPENAI_API_KEY"], timeout=180.0)
    con = dbm.connect()

    con.execute("""CREATE TABLE IF NOT EXISTS subcodes (
        record_id TEXT NOT NULL, theme TEXT NOT NULL, subcode TEXT NOT NULL,
        confidence REAL, run_id TEXT NOT NULL,
        PRIMARY KEY (record_id, theme, subcode, run_id))""")

    todo = []
    for theme in args.themes:
        spec = CROSSWALK["stage_c"].get(theme, {})
        subs = spec.get("subcodes")
        if not subs:
            print(f"  {theme}: no sub-codes defined, skipping")
            continue
        rows = [dict(r) for r in con.execute("""
            SELECT rec.record_id, rec.text_raw, rec.thread_context
            FROM classifications cl JOIN records rec ON rec.record_id = cl.record_id
            WHERE cl.code = ?""", (theme,))]
        print(f"  {theme}: {len(rows)} records, {len(subs)} sub-codes")
        todo += [(theme, subs, r) for r in rows]

    if not todo:
        return 0

    with rmod.Run(con, "subcodes", model=args.model, prompt_version=PROMPT_VERSION) as run:
        run.n_input = len(todo)

        def one(item):
            theme, subs, rec = item
            prompt, ids = theme_prompt(theme, subs)
            ctx = (f"<context nonquotable>{rec['thread_context']}</context nonquotable>\n\n"
                   if rec.get("thread_context") else "")
            r = client.responses.create(
                model=args.model, instructions=prompt,
                input=f"{ctx}<record>\n{rec['text_raw'][:5000]}\n</record>",
                reasoning={"effort": "minimal"},
                text={"format": {"type": "json_schema", "name": "subcodes",
                                 "schema": schema(ids), "strict": True}})
            return theme, rec, json.loads(r.output_text), r.usage

        ok = err = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(one, t) for t in todo]
            for i, f in enumerate(as_completed(futs), 1):
                try:
                    theme, rec, out, usage = f.result()
                except Exception as e:                       # noqa: BLE001
                    err += 1
                    continue
                run.add_usage(input_tokens=usage.input_tokens,
                              output_tokens=usage.output_tokens)
                for sc in out.get("subcodes", []):
                    con.execute(
                        "INSERT OR REPLACE INTO subcodes VALUES (?,?,?,?,?)",
                        (rec["record_id"], theme, sc["subcode"],
                         float(sc["confidence"]), run.run_id))
                ok += 1
                if i % 100 == 0:
                    con.commit()
                    print(f"    {i}/{len(todo)}  ${run.cost_usd() or 0:.2f}", flush=True)
        con.commit()
        run.n_output = ok
        print(f"\n  sub-coded {ok}, errors {err}, cost ${run.cost_usd() or 0:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
