"""One-time repair for classifications written before the C9/C11 pairwise
rule was wired in (EC-CLS-4 / S2-INV-3).

Resolution rule, applied consistently everywhere: POSITIVE EVIDENCE OF
INTENT BEATS THE NO-INTENT CODE. A voiced doubt, or a purchase completed
elsewhere, both prove intent existed — so C9 loses to a Confidence-phase
code and loses to C11.

Removals are logged rather than silent: edgecase.md is explicit that
contradiction violations are "flagged for re-classification", so the count
belongs in the run record.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import codebook as cbm, db as dbm  # noqa: E402


def run(con) -> dict:
    cb = cbm.load()
    per = defaultdict(list)
    for r in con.execute("SELECT record_id, code FROM classifications"):
        per[r["record_id"]].append(r["code"])

    removed = 0
    fixed_records = 0
    for rid, cs in per.items():
        drop: set[str] = set()
        conf = {c for c in cs if cb.codes.get(c, {}).get("phase") == "confidence"}
        if conf:
            drop |= {c for c in cs if c in ("C9", "C11")}
        if "C9" in cs and "C11" in cs:
            drop.add("C9")
        if not drop:
            continue
        for c in drop:
            con.execute("DELETE FROM classifications WHERE record_id=? AND code=?", (rid, c))
            removed += 1
        fixed_records += 1
        # blocking_code may have pointed at a code that no longer exists
        row = con.execute(
            "SELECT blocking_code FROM record_meta WHERE record_id=?", (rid,)).fetchone()
        if row and row["blocking_code"] in drop:
            survivors = [c for c in cs if c not in drop and c in cb.codes]
            if survivors:
                new = min(survivors, key=lambda x: cb.codes[x]["journey_rank"])
                con.execute(
                    "UPDATE record_meta SET blocking_code=?, blocking_phase=? WHERE record_id=?",
                    (new, cb.codes[new]["phase"], rid))
    # Changing blocking_code can leave an outcome the NEW code forbids
    # (S2-INV-4). Re-coerce every row from the codebook, not just repaired
    # ones -- cheap, and it makes the invariant hold by construction rather
    # than by the repair having been careful.
    coerced = 0
    for r in con.execute(
            "SELECT record_id, blocking_code, outcome FROM record_meta"
            " WHERE blocking_code IS NOT NULL").fetchall():
        d = cb.codes.get(r["blocking_code"])
        if d and r["outcome"] and r["outcome"] not in d["outcome_allowed"]:
            con.execute("UPDATE record_meta SET outcome=? WHERE record_id=?",
                        (d["outcome_default"], r["record_id"]))
            coerced += 1

    con.commit()
    return {"records_fixed": fixed_records, "codes_removed": removed,
            "outcomes_coerced": coerced}


if __name__ == "__main__":
    print(run(dbm.connect()))
