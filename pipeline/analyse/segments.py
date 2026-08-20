"""Derive the six segments of the updated framework (2026-08-20).

WHY THIS REPLACES S1/S2/S3. The old segmentation asked "why did you save
it?" -- a motivation public text almost never states. Measured coverage was
6.6%, and of the 79 labelled records 59 were bookmarkers, because collecting
behaviour gets said out loud while urgency does not. The mix was not just
thin, it was biased.

The updated framework asks three STRUCTURAL questions instead:

    Q1  Is there intent to purchase?      -> no / lapsed / yes
    Q2  When do they intend to buy?       -> soon / later
    Q3  Have they decided?                -> yes / no

Every one of those is already answered by the classification pass, so the
segment is DERIVED rather than inferred, and coverage is 100%.

    Q3 = "have they decided" is the presence of an unresolved
    Confidence-phase code. A voiced doubt IS an undecided decision. That is
    the same principle the contradiction rule uses, applied to segmentation.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import codebook as cbm, db as dbm, runs as rmod  # noqa: E402

# Engine codes that indicate a horizon of "later": waiting on a price move,
# a restock, or with no trigger to act. Framework C9 territory.
LATER_CODES = {"C6", "C8", "C13"}
NO_INTENT = {"C9"}          # engine C9 = framework C10, intent never existed
LAPSED = {"C11", "C12"}     # framework C11, intent extinguished after saving

SEGMENTS = {
    1: "Collectors",
    2: "Lapsed Intenders",
    3: "Ready Buyers",
    4: "Stuck Deciders",       # ★ target
    5: "Committed Waiters",
    6: "Hesitant Waiters",
}
TARGET = 4


def derive(codes: set[str], outcome: str | None, confidence_codes: set[str]) -> int:
    # Q1 -- is there intent?
    if outcome == "na" or (codes & NO_INTENT):
        return 1
    if codes & LAPSED:
        return 2
    # Q3 -- decided? An unresolved doubt means no.
    decided = not (codes & confidence_codes)
    # Q2 -- horizon
    later = bool(codes & LATER_CODES)
    if decided:
        return 5 if later else 3
    return 6 if later else 4


def run(con) -> dict:
    cb = cbm.load()
    conf_codes = {k for k, d in cb.codes.items() if d["phase"] == "confidence"}

    codes = defaultdict(set)
    for r in con.execute("SELECT record_id, code FROM classifications"):
        codes[r["record_id"]].add(r["code"])
    # Must honour `exclusions` for the same reason crosstabs does: segments and
    # the barrier ranking are rendered side by side, so a population difference
    # between them is a contradiction on one screen. Before this, segments
    # covered 1,199 records while crosstabs used 1,018.
    meta = {r["record_id"]: dict(r) for r in con.execute(
        """SELECT m.* FROM record_meta m
           WHERE NOT EXISTS (SELECT 1 FROM exclusions e
                             WHERE e.record_id = m.record_id)""")}

    with rmod.Run(con, "segments", model=None, codebook_version=cb.version_string) as R:
        con.execute("""CREATE TABLE IF NOT EXISTS segments_v2 (
            record_id TEXT PRIMARY KEY REFERENCES records(record_id),
            segment_id INTEGER NOT NULL,
            segment_name TEXT NOT NULL,
            has_intent INTEGER, horizon TEXT, decided INTEGER,
            run_id TEXT NOT NULL)""")
        con.execute("DELETE FROM segments_v2")

        counts = Counter()
        for rid, m in meta.items():
            cs = codes.get(rid, set())
            sid = derive(cs, m.get("outcome"), conf_codes)
            counts[sid] += 1
            con.execute(
                "INSERT INTO segments_v2 (record_id, segment_id, segment_name,"
                " has_intent, horizon, decided, run_id) VALUES (?,?,?,?,?,?,?)",
                (rid, sid, SEGMENTS[sid], int(sid not in (1, 2)),
                 "later" if cs & LATER_CODES else "soon",
                 int(not (cs & conf_codes)), R.run_id))

        # segment x code, on 100% coverage this time
        con.execute("""CREATE TABLE IF NOT EXISTS analysis_segment_code_v2 (
            segment_id INTEGER, segment_name TEXT, code TEXT,
            n INTEGER, n_distinct_authors INTEGER, denominator INTEGER,
            share REAL, below_min_n INTEGER, run_id TEXT,
            PRIMARY KEY (segment_id, code, run_id))""")
        con.execute("DELETE FROM analysis_segment_code_v2")

        seg_of = {rid: derive(codes.get(rid, set()), m.get("outcome"), conf_codes)
                  for rid, m in meta.items()}
        authors = {r["record_id"]: r["author_hash"] for r in
                   con.execute("SELECT record_id, author_hash FROM records")}
        for sid in SEGMENTS:
            members = [r for r, s in seg_of.items() if s == sid]
            if not members:
                continue
            per = Counter(c for r in members for c in codes.get(r, set()))
            for code, n in per.items():
                auth = len({authors.get(r) for r in members
                            if code in codes.get(r, set()) and authors.get(r)})
                con.execute(
                    "INSERT OR REPLACE INTO analysis_segment_code_v2 VALUES (?,?,?,?,?,?,?,?,?)",
                    (sid, SEGMENTS[sid], code, n, auth, len(members),
                     n / len(members), int(n < 15), R.run_id))

        con.commit()
        R.n_input = len(meta)
        R.n_output = len(meta)
        return {"counts": dict(counts), "coverage": len(meta)}


if __name__ == "__main__":
    con = dbm.connect()
    out = run(con)
    tot = sum(out["counts"].values())
    print(f"six-segment derivation — coverage {tot}/{tot} = 100%\n")
    for sid, name in SEGMENTS.items():
        n = out["counts"].get(sid, 0)
        star = "  <-- TARGET" if sid == TARGET else ""
        print(f"  {sid}. {name:<20} {n:>5}  {n/tot:>6.1%}{star}")
