"""S1-HUM-1 — draw a random sample of retained records for a human to read.

WHY THIS IS A SCRIPT AND NOT A ONE-OFF QUERY
--------------------------------------------
The check is "read 30 random retained records — are they what you expected?".
Two properties make the answer worth anything, and both need code:

1. **The draw is seeded.** An unseeded sample cannot be re-read, cannot be
   shown to a second person, and cannot be pointed at afterwards when someone
   asks which records the judgement was made on.

2. **Each record carries what the pipeline DECIDED about it.** The check as
   written only asks whether the raw material is right. But a reader who is
   already reading the text can answer a second, sharper question for free —
   did the classifier judge this one sensibly? — and that question has no other
   cheap answer anywhere in the build. A record shown without its verdict wastes
   the read.

WHAT "RETAINED" MEANS HERE
--------------------------
The `retained` view: everything collected that survived cleaning and was not
later excluded — 5,099 records, being 8,647 post-clean minus the 3,548 from the
five low-yield subreddits. It is deliberately the PRE-RELEVANCE population, so
roughly 6 in 7 of these were judged not to bear on the save-to-purchase
decision. That is expected, and it is the point: a sample drawn from the
relevant records alone would show a curated corpus and could not reveal a
collection strategy that aimed at the wrong thing.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.common import db as dbm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260820


def draw(con, n: int, seed: int) -> list[dict]:
    ids = [r[0] for r in con.execute("SELECT record_id FROM retained ORDER BY record_id")]
    picked = random.Random(seed).sample(ids, min(n, len(ids)))

    out = []
    for rid in picked:
        rec = dict(con.execute("""
            SELECT record_id, source, source_url, created_at, text_raw, thread_context,
                   rating, collect_query, lang, text_available
            FROM records WHERE record_id = ?""", (rid,)).fetchone())

        rel = con.execute(
            "SELECT is_relevant, reason, confidence, secondhand, myntra_specific"
            " FROM relevance WHERE record_id = ?", (rid,)).fetchone()
        rec["relevance"] = dict(rel) if rel else None

        rec["codes"] = [dict(r) for r in con.execute("""
            SELECT code, confidence, is_blocking, evidence_span, span_verified, reasoning
            FROM classifications WHERE record_id = ? ORDER BY is_blocking DESC, confidence DESC""",
            (rid,))]

        meta = con.execute(
            "SELECT blocking_code, outcome, intensity, workaround, workaround_text,"
            " counterfactual, counterfactual_text FROM record_meta WHERE record_id = ?",
            (rid,)).fetchone()
        rec["meta"] = dict(meta) if meta else None

        seg = con.execute(
            "SELECT segment_id, segment_name FROM segments_v2 WHERE record_id = ?",
            (rid,)).fetchone()
        rec["segment"] = dict(seg) if seg else None

        gold = con.execute("SELECT 1 FROM gold WHERE record_id = ? LIMIT 1", (rid,)).fetchone()
        rec["in_gold"] = bool(gold)
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default=str(ROOT / "data" / "artifacts" / "s1_hum_1_sample.json"))
    a = ap.parse_args()

    con = dbm.connect(read_only=True)
    sample = draw(con, a.n, a.seed)
    total = con.execute("SELECT count(*) FROM retained").fetchone()[0]
    payload = {"check": "S1-HUM-1", "population": "retained", "population_n": total,
               "n": len(sample), "seed": a.seed, "records": sample}
    Path(a.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    rel = sum(1 for r in sample if (r["relevance"] or {}).get("is_relevant"))
    print(f"{len(sample)} of {total:,} retained records, seed {a.seed} -> {a.out}")
    print(f"  judged relevant: {rel}  ·  judged not relevant: {len(sample) - rel}")
    print(f"  by source: ", end="")
    from collections import Counter
    print(dict(Counter(r["source"] for r in sample)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
