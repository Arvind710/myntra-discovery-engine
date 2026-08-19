"""Draw the gold sampling frame — implementationplan.md Appendix B.

WHY THE FRAME IS NOT "a random sample of what we classified"
------------------------------------------------------------
architecture.md §6.6 drew gold from pilot output: records that survived
every filter and got classified. Appendix B corrects that, because the same
gold set is asked to measure *recall* — T-2 (relevance recall >= 85%). A
sample containing only survivors makes recall trivially 100% and prints a
passing grade for a question it never asked. So the frame deliberately
over-samples the places the pipeline is most likely to be wrong, and
includes records the pipeline THREW AWAY.

AMENDMENT, 2026-08-20 (Arvind)
------------------------------
Appendix B allocated 25 slots to a `prefilter_rejected` stratum to measure
T-5 prefilter recall. That stratum is retired: the prefilter was scored
against both pools directly, measured 76.6% against a T-5 floor of 95%, and
was dropped from the pipeline. The question is answered and the component
is gone, so the slots buy nothing.

They move to `rel_zero` (25 -> 50), on this reasoning: relevance is the pass
we cannot afford to redo. It cost $5.36 against $1.87 for classification, so
a classification failure is recoverable by re-running and a relevance
failure is not. 7,440 records sit in the judged-irrelevant pool and not one
has been read by a human. Doubling the stratum roughly halves the width of
the T-2 interval on the pass whose failure would be permanent.

BLINDING
--------
The frame stores no model output — no code, no confidence, no relevance
verdict. `9_Label.py` renders text and nothing else. A gold set that shows
the labeller what the model said measures agreement with a suggestion, not
independent judgement, and it would inflate every metric downstream while
looking exactly like a clean result.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from pipeline.common import db, runs  # noqa: E402

SEED = 20260820

# Appendix B as amended. Order matters: strata are filled top-down and a
# record already taken is never offered to a later stratum, so the scarcest
# and most diagnostic pools are satisfied first.
STRATA: list[tuple[str, int, str]] = [
    ("z99",       20, "Is the 31.7% residual a real gap in the world, or a hole "
                      "in the codebook? AC-11 turns on this."),
    ("c1_c8",     20, "The named danger pair — C1 fit-uncertainty vs C8 "
                      "size-unavailable have OPPOSITE solves. T-7 / EC-CLS-12."),
    ("clf_low",   30, "Where the classifier is weakest, over-sampled on purpose."),
    ("clf_high",  40, "Baseline agreement — T-3, T-4."),
    ("rel_zero",  50, "Records the relevance pass discarded. The ONLY way T-2 "
                      "recall is measurable at all."),
]
N_REPEATS = 20          # T-13 intra-rater, silently repeated in sitting 2
SITTINGS = ("sitting-1", "sitting-2")


def _pools(con) -> dict[str, list[tuple[str, str]]]:
    """(record_id, source) candidate lists, richest diagnostic pool first."""
    q = lambda sql: [(r["record_id"], r["source"]) for r in con.execute(sql)]
    return {
        "z99": q("""SELECT DISTINCT c.record_id, r.source
                    FROM classifications c JOIN records r USING (record_id)
                    WHERE c.code LIKE 'Z%'"""),
        "c1_c8": q("""SELECT DISTINCT c.record_id, r.source
                      FROM classifications c JOIN records r USING (record_id)
                      WHERE c.code IN ('C1','C8')"""),
        # Mean confidence across a record's codes. Ties broken by record_id so
        # the split is deterministic rather than dependent on scan order.
        "clf_low": q("""SELECT c.record_id, r.source
                        FROM classifications c JOIN records r USING (record_id)
                        GROUP BY c.record_id
                        ORDER BY avg(c.confidence) ASC, c.record_id"""),
        "clf_high": q("""SELECT c.record_id, r.source
                         FROM classifications c JOIN records r USING (record_id)
                         GROUP BY c.record_id
                         ORDER BY avg(c.confidence) DESC, c.record_id"""),
        "rel_zero": q("""SELECT v.record_id, r.source
                         FROM relevance v JOIN records r USING (record_id)
                         WHERE v.is_relevant = 0"""),
    }


def _spread(candidates: list[tuple[str, str]], n: int, rng: random.Random,
            ordered: bool) -> list[str]:
    """Take n, spread across sources (Appendix B: per-source behaviour must be
    visible, EC-VAL-4). Round-robin over per-source queues gives every source
    representation before any source gets a second slot.

    `ordered` preserves the incoming order within each source — used by the
    confidence strata, where position in the list IS the selection criterion.
    Shuffling those would silently turn "lowest confidence" into "random".
    """
    by_source: dict[str, list[str]] = defaultdict(list)
    for rid, src in candidates:
        by_source[src].append(rid)
    if not ordered:
        for v in by_source.values():
            rng.shuffle(v)

    # Rotate the source order per call so the same source is not always the
    # one that gets the odd remaining slot.
    sources = sorted(by_source)
    rng.shuffle(sources)

    picked: list[str] = []
    while len(picked) < n and any(by_source[s] for s in sources):
        for s in sources:
            if len(picked) == n:
                break
            if by_source[s]:
                picked.append(by_source[s].pop(0))
    return picked


def sample(con, *, force: bool = False) -> str:
    existing = con.execute("SELECT count(*) FROM gold_sample").fetchone()[0]
    if existing and not force:
        raise SystemExit(
            f"gold_sample already holds {existing} rows. The frame is drawn ONCE and "
            "frozen — redrawing after labelling has begun silently changes what the "
            "metrics were computed over. Pass --force only if no labels exist yet.")
    if existing and force:
        labelled = con.execute("SELECT count(*) FROM gold").fetchone()[0]
        if labelled:
            raise SystemExit(
                f"refusing to redraw: {labelled} gold labels already exist. Those "
                "hours would be discarded and the strata would no longer match.")

    rng = random.Random(SEED)
    pools = _pools(con)
    taken: set[str] = set()
    assigned: list[tuple[str, str]] = []   # (record_id, stratum)

    for name, n, _why in STRATA:
        avail = [(rid, src) for rid, src in pools[name] if rid not in taken]
        ordered = name in ("clf_low", "clf_high")
        got = _spread(avail, n, rng, ordered)
        if len(got) < n:
            print(f"  ! {name}: only {len(got)} of {n} available")
        taken.update(got)
        assigned += [(rid, name) for rid in got]

    # Split every stratum across both sittings, so fatigue and drift land
    # evenly rather than concentrating in whichever stratum went last.
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for rid, st in assigned:
        by_stratum[st].append(rid)

    rows: list[tuple] = []
    s1: list[str] = []
    for st, rids in by_stratum.items():
        rng.shuffle(rids)
        half = len(rids) // 2
        for i, rid in enumerate(rids):
            sitting = SITTINGS[0] if i < half else SITTINGS[1]
            if sitting == SITTINGS[0]:
                s1.append(rid)
            rows.append((rid, 1, st, sitting))

    # T-13 / EC-VAL-1: 20 sitting-1 records shown again in sitting 2. "Silently"
    # is the whole point — the labeller must not know, or they answer from
    # memory and the number measures recall of their own label.
    repeats = rng.sample(s1, min(N_REPEATS, len(s1)))
    stratum_of = {rid: st for rid, st in assigned}
    rows += [(rid, 2, stratum_of[rid], SITTINGS[1]) for rid in repeats]

    # Interleave within each sitting so strata are not presented in blocks —
    # a run of 20 Z-99 records in a row invites a different standard than the
    # same records scattered.
    out: list[tuple] = []
    for sitting in SITTINGS:
        batch = [r for r in rows if r[3] == sitting]
        rng.shuffle(batch)
        for seq, (rid, pass_no, st, sit) in enumerate(batch, start=1):
            out.append((rid, pass_no, st, sit, seq))

    with runs.Run(con, "gold-sample", seed=SEED,
                  frame="Appendix B as amended 2026-08-20",
                  amendment="prefilter_rejected 25 -> rel_zero (25->50)") as run:
        run.n_input = sum(len(v) for v in pools.values())
        con.executemany(
            "INSERT INTO gold_sample (record_id, pass_no, stratum, sitting_id, seq, run_id)"
            " VALUES (?,?,?,?,?,?)", [(*r, run.run_id) for r in out])
        con.commit()
        run.n_output = len(out)
        run_id = run.run_id

    return run_id


def report(con) -> None:
    # pass_no=1 only. A repeat is the SAME record a second time, so counting it
    # into its stratum would report 22 distinct Z-99 records when there are 20.
    print("\n  stratum      sitting-1  sitting-2  distinct   +repeats")
    for name, want, _ in STRATA:
        a = con.execute("SELECT count(*) FROM gold_sample WHERE stratum=? AND sitting_id=?"
                        " AND pass_no=1", (name, SITTINGS[0])).fetchone()[0]
        b = con.execute("SELECT count(*) FROM gold_sample WHERE stratum=? AND sitting_id=?"
                        " AND pass_no=1", (name, SITTINGS[1])).fetchone()[0]
        rep = con.execute("SELECT count(*) FROM gold_sample WHERE stratum=? AND pass_no=2",
                          (name,)).fetchone()[0]
        flag = "" if a + b == want else f"  (target {want})"
        print(f"  {name:11}  {a:>9}  {b:>9}  {a+b:>8}  {rep:>9}{flag}")
    distinct = con.execute("SELECT count(DISTINCT record_id) FROM gold_sample").fetchone()[0]
    reps = con.execute("SELECT count(*) FROM gold_sample WHERE pass_no=2").fetchone()[0]
    items = con.execute("SELECT count(*) FROM gold_sample").fetchone()[0]
    print(f"\n  distinct records : {distinct}")
    print(f"  silent repeats   : {reps}")
    print(f"  items to label   : {items}")

    print("\n  by source:")
    for r in con.execute("""SELECT r.source, count(*) n FROM gold_sample g
                            JOIN records r USING (record_id) WHERE g.pass_no=1
                            GROUP BY r.source ORDER BY n DESC"""):
        print(f"    {r['source']:10} {r['n']:>4}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Draw the Appendix B gold frame")
    ap.add_argument("--force", action="store_true",
                    help="redraw (refused once any label exists)")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()

    con = db.connect()
    if not a.report_only:
        rid = sample(con, force=a.force)
        print(f"frame drawn: {rid}")
    report(con)
