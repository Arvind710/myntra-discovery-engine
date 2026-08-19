"""Recorded amendments to the gold set — EC-VAL-5.

Gold is one person's judgement, not ground truth, and it may be corrected —
but never silently. Every amendment below names the record, the change, and
the frozen definition the original label contradicted. The reason is written
into `gold.notes`, so a reviewer reading the database can reconstruct exactly
what was changed and why without taking anyone's word for it.

WHY THESE NINE
--------------
All nine sit in the `rel_zero` stratum: records the relevance pass DISCARDED
and the labeller marked relevant. Left standing they produced the single most
alarming number in the first scoring run — 23.1% of discarded records
apparently relevant, extrapolating to ~1,700 lost records, more than the
entire kept corpus.

Eight of them share one mistake: a positive post-purchase review coded as the
doubt-code for the topic it mentions. "Very nice. Good fabric and print" was
coded C2, whose boundary note reads "DOUBT about the PHYSICAL PROPERTIES of
the garment versus its depiction" — praise is its opposite. "Awesome variety
of options" was coded C3. The codes are barriers that BLOCKED a purchase, not
topics a comment touches.

That is a user-interface failure as much as a labelling one: the tool showed
"C2 · Physical-vs-digital gap" with nothing on screen to say the task is to
code what STOPPED someone. The fix belongs in the tool as well as the data,
and is applied there too.

The ninth is different and is a genuine catch by the labeller — MRP tampering
IS a purchase-relevant doubt. It was coded C2 (material) when C6 explicitly
covers "suspicion that the discount is fake". Relevance upheld, code corrected.

WHAT THIS DOES NOT DO
---------------------
It does not touch any label the labeller and the model disagreed on as a
matter of judgement. Order-cancellation and service complaints marked
not-relevant stay not-relevant: that is a defensible reading of the relevance
bar, not a definitional violation, and overriding it would be substituting my
judgement for the labeller's, which is exactly what gold exists to prevent.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm  # noqa: E402

PRAISE = ("Amended 2026-08-20 (Arvind's approval): positive post-purchase review, "
          "not a barrier. Coded as the doubt-code for the topic mentioned; the "
          "codebook boundary for that code requires DOUBT, which praise is the "
          "opposite of. Marked not relevant.")

AMENDMENTS: list[tuple[str, int, list[str], str]] = [
    ("9afdbb8d4706ac7b0563ab2b47cbed7f0b97a29b", 0, [],
     "Amended 2026-08-20 (Arvind's approval): request for a makeup-haul video. "
     "No saved item and no purchase decision, so outside the relevance frame. "
     "C6 requires value/price doubt about a considered purchase."),
    ("925eb6c740bc6717bfac4f36e63a3d653e8424b1", 0, [],
     "Amended 2026-08-20 (Arvind's approval): complaint about customer-service "
     "call options. C7 requires anticipated RETURN/DELIVERY risk suppressing a "
     "decision BEFORE purchase; post-hoc service contact is not that."),
    ("5b7d8c5d499a6f8615fee0fbd2c5fe7bd80e265f", 0, [], PRAISE),
    ("3cc8c000382aa4a66bf45c98f93857cf6a8bd540", 0, [],
     "Amended 2026-08-20 (Arvind's approval): Facebook-affiliate connection "
     "problem. C10 requires ANOTHER PERSON's approval — spousal/parental/budget "
     "permission — not an app permission or login fault."),
    ("6dd7a312cbd830a1c98cbee3686284a483a5eabb", 0, [], PRAISE),
    ("2cd6526c8db94c7eaee02638e6b0611753f945f4", 0, [],
     "Amended 2026-08-20 (Arvind's approval): comment on a garment's look in "
     "media. No purchase decision and no third-party approval; C10 does not apply."),
    ("9367624918ef69a7b762833fe0b9b17e504df548", 0, [], PRAISE),
    ("14137a4849abf393f38a1e854c7ed6b5d2f6ad72", 1, ["C6"],
     "Amended 2026-08-20 (Arvind's approval): RELEVANCE UPHELD — MRP tampering is "
     "a genuine purchase-relevant doubt and the labeller was right that the "
     "classifier missed it. Code corrected C2 -> C6: C6 explicitly covers "
     "'suspicion that the discount is fake'; C2 is material/quality doubt."),
    ("99f142562ca29cb76058147f3bf4732ffb5a1681", 0, [], PRAISE),
]


def apply(con: sqlite3.Connection, *, dry_run: bool = False) -> int:
    n = 0
    for rec_id, is_rel, codes, reason in AMENDMENTS:
        row = con.execute(
            "SELECT is_relevant, codes, notes FROM gold WHERE record_id=? AND pass_no=1",
            (rec_id,)).fetchone()
        if row is None:
            print(f"  ! {rec_id[:8]} not in gold — skipped")
            continue
        before = f"was relevant={row['is_relevant']} codes={row['codes']}"
        if int(row["is_relevant"]) == is_rel and json.loads(row["codes"]) == codes:
            print(f"  = {rec_id[:8]} already in the amended state")
            continue
        print(f"  ~ {rec_id[:8]} {before} -> relevant={is_rel} codes={codes}")
        if not dry_run:
            # The prior label is preserved inside the note: an amendment that
            # erases what it replaced cannot be audited.
            note = f"{reason} [prior label: {before}]"
            con.execute(
                "UPDATE gold SET is_relevant=?, codes=?, segment=NULL, notes=?,"
                " labelled_at=? WHERE record_id=? AND pass_no=1",
                (is_rel, json.dumps(codes), note,
                 datetime.now(timezone.utc).isoformat(timespec="seconds"), rec_id))
        n += 1
    if not dry_run:
        con.commit()
    return n


if __name__ == "__main__":
    dry = "--apply" not in sys.argv
    con = dbm.connect()
    print("DRY RUN — pass --apply to write\n" if dry else "APPLYING\n")
    n = apply(con, dry_run=dry)
    print(f"\n{n} amendment(s) {'would be' if dry else ''} applied")
