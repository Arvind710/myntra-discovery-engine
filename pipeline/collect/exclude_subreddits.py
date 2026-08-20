"""Exclude the low-yield subreddits — a marked, reversible source decision.

WHY
---
Arvind noticed that r/mumbai records were mostly not about online fashion. The
audit confirmed it and found worse nearby, measured against his own gold labels
and the relevance pass:

    subreddit              scored  relevant   yield   FP rate (gold)
    IndianFashionAddicts      544       212   39.0%   1 of 5
    TwoXIndia                 197        73   37.1%   0 of 1
    IndianFashion             100        24   24.0%   0 of 1
    mumbai                    717        89   12.4%   4 of 7   <-- 57%
    india                    1151        69    6.0%   2 of 5
    delhi                     531        22    4.1%   0 of 1
    bangalore                 692         1    0.1%   -
    IndiaTech                 457         0    0.0%   -

r/bangalore returned ONE relevant record from 692, and r/IndiaTech none from
457. r/mumbai's 89 "relevant" records are 2% Myntra-specific, and the gold set
puts its false-positive rate at 4 of 7.

WHY THIS IS SAFE, AND WHY IT STRENGTHENS THE RESULT
---------------------------------------------------
Removing all 181 relevant records from these five (15.1% of the corpus) leaves
the barrier ranking IDENTICAL — every code holds its position and no share
moves more than 1.5pp. So nothing analytical is lost, and what is gained is a
sensitivity result worth stating plainly: the conclusions survive deleting the
noisiest sixth of the evidence.

The records are MARKED, not deleted ([A.1]) — they stay in `records`, stay
visible in the Data Bank's exclusion log with this reason, and the decision is
reversible by deleting these rows.

ALSO FOUND
----------
r/DesiFashion was configured in SUBREDDITS and collected ZERO records. A source
that silently returns nothing looks identical to a source with nothing to say;
recorded here because no check caught it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm  # noqa: E402
from pipeline.common import runs as rmod  # noqa: E402

DROP = {"mumbai", "india", "bangalore", "IndiaTech", "delhi"}
DETAIL = "low-yield subreddit: general/city community, not a fashion-shopping forum"


def subreddit_of(thread_context: str | None, url: str | None) -> str | None:
    m = re.match(r"r/([A-Za-z0-9_]+)", thread_context or "")
    if not m:
        m = re.search(r"reddit\.com/r/([A-Za-z0-9_]+)", url or "")
    return m.group(1) if m else None


def main() -> int:
    con = dbm.connect()
    rows = con.execute(
        "SELECT record_id, source, thread_context, source_url FROM records "
        "WHERE source='reddit'").fetchall()
    targets = [(r["record_id"], r["source"]) for r in rows
               if subreddit_of(r["thread_context"], r["source_url"]) in DROP]
    if not targets:
        print("nothing to exclude")
        return 0

    before = con.execute(
        "SELECT count(*) FROM relevance WHERE is_relevant=1").fetchone()[0]
    with rmod.Run(con, "exclude-subreddits", dropped=sorted(DROP)) as run:
        run.n_input = len(targets)
        con.executemany(
            "INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason,"
            " detail, run_id) VALUES (?,?,?,?,?,?)",
            [(rid, src, "collect", "other", DETAIL, run.run_id) for rid, src in targets])
        con.commit()
        run.n_output = len(targets)

    after = con.execute(
        """SELECT count(*) FROM relevance v WHERE v.is_relevant=1
           AND NOT EXISTS (SELECT 1 FROM exclusions e WHERE e.record_id=v.record_id)"""
    ).fetchone()[0]
    print(f"marked {len(targets)} records across {sorted(DROP)}")
    print(f"relevant corpus for analysis: {before} -> {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
