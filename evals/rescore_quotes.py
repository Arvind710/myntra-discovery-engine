"""Re-apply the corrected quote check to a completed sweep, in place.

WHY THIS IS LEGITIMATE, AND WHERE IT STOPS
------------------------------------------
A checker correction is exactly the thing you re-apply to an existing run. The
answers do not change; only the measurement of them does. Re-buying the sweep
would test the model's run-to-run variance, which is not what a fixed checker
needs establishing.

But it is only legitimate for checks that can be recomputed FAITHFULLY from
what the artefact stores, and that is a short list:

  check_quotes    needs the retrieved RECORDS — stored as `record_ids`. ✅
  check_uncited   needs only the answer text.                            ✅
  check_numerals  needs the retrieved analysis ROWS — NOT stored.        ❌
  check_citations needs the retrieved analysis ROWS — NOT stored.        ❌

So this script recomputes ONLY the quote check, and leaves every other finding
exactly as it was measured during the run with the real retrieval context. The
two it cannot recompute are unaffected in any case: the only verifier change
made after the sweep was to `check_quotes` (quote-character normalisation, and
scoping testimony to the section that presents it), and neither touches
numerals or citations.

The artefact records what was done, so the gate report is never reading a
number whose provenance is unclear.

Usage:
    python evals/rescore_quotes.py            # rewrites p4_sweep_latest.json
    python evals/rescore_quotes.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

REPORTS = ROOT / "evals" / "reports"
LATEST = REPORTS / "p4_sweep_latest.json"

NOTE = (
    "`bad_quotes` was recomputed after the run with a corrected quote check; "
    "every other finding is as measured during the run against the real "
    "retrieval context. Two corrections applied: all quote characters now "
    "normalise to one form (a model nesting a quotation converts the inner "
    "pair, which made a genuine elided quote look fabricated), and the "
    "absolute testimony threshold is scoped to the section that presents "
    "testimony. Quotes outside it are prose and are listed as `advisory_quotes`."
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    from lib import db as appdb
    from lib import verify as V

    con = appdb.connection()
    d = json.loads(LATEST.read_text())

    fixtures = {}
    for line in (ROOT / "evals" / "fixtures" / "injection_records.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            fixtures[r["record_id"]] = r

    before = sum(len(r.get("bad_quotes") or []) for r in d["results"])
    after = 0
    for r in d["results"]:
        recs = []
        for rid in (r.get("record_ids") or []):
            if rid in fixtures:
                recs.append({**fixtures[rid], "_cite": {"table": "record", "key": rid}})
                continue
            row = con.execute("SELECT * FROM records WHERE record_id = ?", (rid,)).fetchone()
            if row:
                recs.append({**dict(row), "_cite": {"table": "record", "key": rid}})

        stale = set(r.get("bad_quotes") or [])
        fresh = V.check_quotes(r.get("answer") or "", recs, [])
        r["bad_quotes"] = fresh
        after += len(fresh)

        # `problems` is what the gate tests read. Drop the stale quote entries
        # and add the surviving ones, leaving every other finding untouched.
        kept = [p for p in (r.get("problems") or [])
                if not (p.startswith("unverifiable quote:")
                        and p.split(": ", 1)[1] in stale)]
        r["problems"] = [f"unverifiable quote: {q}" for q in fresh] + kept
        r["verified"] = not r["problems"]

    d["rescored_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    d["rescore_note"] = NOTE
    print(f"unverifiable quotes: {before} -> {after}")
    print(f"answers passing verification: "
          f"{sum(1 for r in d['results'] if r['verified'])}/{len(d['results'])}")
    if a.dry_run:
        print("(dry run — nothing written)")
        return 0
    payload = json.dumps(d, indent=2, ensure_ascii=False)
    LATEST.write_text(payload)
    (REPORTS / f"p4_sweep_{d['run_id']}.json").write_text(payload)
    print(f"rewrote p4_sweep_{d['run_id']}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
