"""Score the pipeline against the gold set — AC-9, T-1 through T-7.

THE THING THAT MAKES THESE NUMBERS HARD TO READ
-----------------------------------------------
The Appendix B frame is deliberately NOT a representative sample. It
over-samples the places the classifier is most likely to be wrong: the lowest
confidence band, the C1/C8 danger pair, the Z-99 residual, and the pool the
relevance pass threw away. That is the right design for FINDING errors and the
wrong design for ESTIMATING a rate, and the plan's thresholds (T-1 accuracy
>= 80%, T-3 agreement >= 70%) are written as if the sample were representative.

Pooling the strata therefore produces a number that is real but pessimistic —
it is agreement on a corpus made mostly of hard cases, not agreement on the
corpus. Weighting the strata back to population size fixes that only where a
stratum is a clean random sample of a population it can be weighted to.

So this module reports three things and keeps them apart:

  * **Per stratum** — always valid, and the most informative view.
  * **Population estimates**, for the three strata that admit them:
    `rel_zero` (50 drawn from 7,440), `z99` (20 from 380), `c1_c8` (20 from
    212). Each is a random draw from a defined population, so a weighted
    estimate is legitimate.
  * **`clf_low` / `clf_high` separately and unweighted.** These are the two
    TAILS of the same confidence ordering; the middle of the distribution was
    never sampled. No weighting can recover a population mean from two tails,
    and pretending otherwise would manufacture precision. They answer "how bad
    is it where it is least sure / most sure", which is what they were drawn
    to answer.

The single most defensible number here does not need any of that machinery:
of the records the relevance pass DISCARDED, what share were actually
relevant? That is a clean random sample of a known population, and it bounds
what the corpus is missing.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm  # noqa: E402

# Populations each stratum was drawn from. Only these three are weightable —
# see the module docstring for why the confidence tails are not.
WEIGHTABLE = {"rel_zero": "SELECT count(*) FROM relevance WHERE is_relevant=0",
              "z99": "SELECT count(DISTINCT record_id) FROM classifications WHERE code LIKE 'Z%'",
              "c1_c8": "SELECT count(DISTINCT record_id) FROM classifications "
                       "WHERE code IN ('C1','C8')"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval. At n=20 a normal approximation is not defensible, and
    every stratum here is small by design."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def kappa(a: list[int], b: list[int]) -> float | None:
    """Cohen's kappa for one code, presence/absence. None when the code is
    absent from both — kappa is undefined there, and reporting 0.0 would read
    as total disagreement rather than "no information"."""
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa1, pb1 = sum(a) / n, sum(b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if pe >= 1.0:
        return None
    return (po - pe) / (1 - pe)


def load(con) -> list[dict]:
    rows = []
    for r in con.execute("""
            SELECT g.record_id, g.pass_no, s.stratum, g.is_relevant AS gold_rel,
                   g.codes AS gold_codes, v.is_relevant AS model_rel
            FROM gold g
            JOIN gold_sample s ON s.record_id=g.record_id AND s.pass_no=g.pass_no
            LEFT JOIN relevance v ON v.record_id=g.record_id
            WHERE g.pass_no = 1"""):
        d = dict(r)
        d["gold_codes"] = set(json.loads(d["gold_codes"]))
        d["model_codes"] = {x[0] for x in con.execute(
            "SELECT DISTINCT code FROM classifications WHERE record_id=?", (d["record_id"],))}
        d["model_rel"] = 0 if d["model_rel"] is None else int(d["model_rel"])
        rows.append(d)
    return rows


def report(con) -> None:
    rows = load(con)
    if not rows:
        raise SystemExit("no gold labels yet")
    print(f"GOLD SCORING — {len(rows)} labelled records (pass 1)\n" + "=" * 66)

    # ---------------------------------------------------------------- relevance
    print("\nRELEVANCE, per stratum")
    print(f"  {'stratum':10} {'n':>4} {'agree':>6} {'acc':>7}   95% CI")
    by_str = defaultdict(list)
    for d in rows:
        by_str[d["stratum"]].append(d)
    for st in sorted(by_str):
        g = by_str[st]
        k = sum(d["gold_rel"] == d["model_rel"] for d in g)
        lo, hi = wilson(k, len(g))
        print(f"  {st:10} {len(g):>4} {k:>6} {k/len(g):>6.1%}   [{lo:.0%}–{hi:.0%}]")

    pooled = sum(d["gold_rel"] == d["model_rel"] for d in rows)
    print(f"\n  pooled (NOT a population estimate — hard cases over-sampled): "
          f"{pooled}/{len(rows)} = {pooled/len(rows):.1%}")

    # T-2: what the relevance pass threw away. The robust headline.
    rz = by_str.get("rel_zero", [])
    if rz:
        missed = sum(d["gold_rel"] == 1 for d in rz)
        lo, hi = wilson(missed, len(rz))
        pop = con.execute(WEIGHTABLE["rel_zero"]).fetchone()[0]
        print(f"\n  ** Of records the classifier DISCARDED, {missed}/{len(rz)} = "
              f"{missed/len(rz):.1%} were actually relevant [{lo:.0%}–{hi:.0%}]")
        print(f"     Extrapolated over the {pop:,} discarded records: "
              f"~{pop*missed/len(rz):,.0f} relevant records lost "
              f"({pop*lo:,.0f}–{pop*hi:,.0f}).")
        kept = con.execute("SELECT count(*) FROM relevance WHERE is_relevant=1").fetchone()[0]
        # Recall needs the purity of the KEPT pool. The classified strata are
        # tails, so this is an estimate with a stated assumption, not a measurement.
        keptrows = [d for d in rows if d["stratum"] != "rel_zero"]
        if keptrows:
            purity = sum(d["gold_rel"] == 1 for d in keptrows) / len(keptrows)
            tp = kept * purity
            fn = pop * missed / len(rz)
            print(f"\n  T-2 relevance recall ~= {tp/(tp+fn):.1%}  (threshold >= 85%) "
                  f"{'PASS' if tp/(tp+fn) >= 0.85 else 'FAIL'}")
            print(f"     ASSUMES the kept pool's true-relevant share ({purity:.1%}) "
                  "generalises from tail-sampled strata. Treat as indicative.")

    # ---------------------------------------------------------------- codes
    both = [d for d in rows if d["gold_rel"] == 1 and d["model_rel"] == 1]
    print(f"\n\nCODES — {len(both)} records both call relevant")
    if not both:
        print("  none yet"); return

    codes = sorted({c for d in both for c in (d["gold_codes"] | d["model_codes"])})
    print(f"\n  {'code':7} {'gold':>5} {'model':>6} {'both':>5} {'agree':>7} {'kappa':>7}")
    kappas = {}
    for c in codes:
        a = [1 if c in d["gold_codes"] else 0 for d in both]
        b = [1 if c in d["model_codes"] else 0 for d in both]
        agree = sum(x == y for x, y in zip(a, b)) / len(both)
        kp = kappa(a, b)
        kappas[c] = kp
        both_n = sum(x and y for x, y in zip(a, b))
        print(f"  {c:7} {sum(a):>5} {sum(b):>6} {both_n:>5} {agree:>6.1%} "
              f"{'  n/a' if kp is None else f'{kp:>7.2f}'}")

    micro = sum(
        sum((1 if c in d["gold_codes"] else 0) == (1 if c in d["model_codes"] else 0)
            for c in codes) for d in both) / (len(both) * len(codes))
    exact = sum(d["gold_codes"] == d["model_codes"] for d in both) / len(both)
    print(f"\n  T-3 per-code agreement (micro, presence/absence): {micro:.1%} "
          f"(threshold >= 70%) {'PASS' if micro >= 0.70 else 'FAIL'}")
    print(f"      exact whole-set match, a much stricter view:    {exact:.1%}")

    scored = {c: k for c, k in kappas.items() if k is not None}
    if scored:
        ok = sum(1 for k in scored.values() if k >= 0.60)
        print(f"  T-4 kappa >= 0.60: {ok}/{len(scored)} codes "
              f"(median {sorted(scored.values())[len(scored)//2]:.2f})")

    # T-7 — the named danger pair
    c1c8 = [d for d in both if {"C1", "C8"} & (d["gold_codes"] | d["model_codes"])]
    if c1c8:
        cross = sum(1 for d in c1c8
                    if ("C1" in d["gold_codes"] and "C8" in d["model_codes"])
                    or ("C8" in d["gold_codes"] and "C1" in d["model_codes"]))
        print(f"\n  T-7 C1<->C8 cross-assignment: {cross}/{len(c1c8)} = "
              f"{cross/len(c1c8):.1%} (threshold <= 15%) "
              f"{'PASS' if cross/len(c1c8) <= 0.15 else 'FAIL'}")

    # T-13 — only meaningful once sitting 2 repeats exist
    reps = con.execute("""
        SELECT g1.codes a, g2.codes b, g1.is_relevant ra, g2.is_relevant rb
        FROM gold g1 JOIN gold g2
          ON g1.record_id=g2.record_id AND g1.pass_no=1 AND g2.pass_no=2""").fetchall()
    if reps:
        same = sum(1 for r in reps
                   if set(json.loads(r["a"])) == set(json.loads(r["b"]))
                   and r["ra"] == r["rb"])
        print(f"\n  T-13 intra-rater agreement: {same}/{len(reps)} = "
              f"{same/len(reps):.1%} (threshold >= 85%)")
    else:
        print("\n  T-13 intra-rater: no repeated items labelled yet (sitting 2)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Score the pipeline against gold")
    ap.parse_args()
    con = dbm.connect()
    con.row_factory = __import__("sqlite3").Row
    report(con)
