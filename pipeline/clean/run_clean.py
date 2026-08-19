"""Cleaning stage orchestrator.

ORDER MATTERS:
  1. scrub    -- PII out before anything else reads or hashes the text
  2. language -- tag (never drop)
  3. dedupe   -- exact across sources, near-dupe WITHIN author only

Every removal is written to `exclusions`, which is a MARKING table: the
record stays in `records` and drops out of the `retained` view. That is
what makes the exclusion log browsable (FR-1.6) and lets the gold sampler
draw from records the filters rejected (Appendix B).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.clean import dedupe, language, scrub  # noqa: E402
from pipeline.common import db as dbm, runs as rmod  # noqa: E402


def main() -> int:
    con = dbm.connect()
    with rmod.Run(con, "clean", model=None) as run:
        n_in = con.execute("SELECT count(*) FROM records").fetchone()[0]
        run.n_input = n_in
        print(f"input: {n_in} records\n")

        s = scrub.run(con, run.run_id)
        print(f"scrub    : {s['scrubbed']} records had PII replaced with placeholders")
        print(f"           {s['too_short']} too short, {s['emoji_only']} emoji-only -> excluded")

        langs = language.run(con, run.run_id)
        print("language : " + "  ".join(f"{k}={v}" for k, v in sorted(langs.items(), key=lambda x: -x[1])))

        d = dedupe.run(con, run.run_id)
        print(f"dedupe   : {d['exact']} exact (cross-source), {d['near']} near (SAME AUTHOR ONLY)")

        retained = con.execute("SELECT count(*) FROM retained").fetchone()[0]
        excluded = con.execute("SELECT count(DISTINCT record_id) FROM exclusions").fetchone()[0]
        run.n_output = retained

        print(f"\nretained : {retained}")
        print(f"excluded : {excluded}")
        print(f"identity : {n_in} == {retained} + {excluded} -> "
              f"{'OK' if n_in == retained + excluded else 'VIOLATION (S1-INV-1)'}")

        authors = con.execute(
            "SELECT count(DISTINCT author_hash) FROM retained WHERE author_hash IS NOT NULL"
        ).fetchone()[0]
        print(f"distinct authors: {authors}  ({retained/max(authors,1):.1f} records per author)")

        top = con.execute(
            "SELECT n_similar_xauthor AS n, count(*) AS c FROM consensus"
            " WHERE n_similar_xauthor > 0 GROUP BY n ORDER BY n DESC LIMIT 3").fetchall()
        if top:
            print("consensus (cross-author echoes, measured NOT removed): "
                  + ", ".join(f"{r['c']} records echoed by {r['n']} authors" for r in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
