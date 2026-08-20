"""Opportunity scoring, its sensitivity, and the segment recommendation.

Discharges implementationplan.md tasks 3.3, 3.5, 3.6, 3.7 and the gate rows
S3-INV-4, S3-INV-5, S3-MET-2, S3-MET-3. Entirely deterministic: no model call,
one seeded random stream. Re-running it reproduces every number (NFR-3).

    opportunity = w1*prevalence + w2*intensity + w3*defer_share
                + w4*solvable_without_money + w5*evidence_strength + w6*segment_fit

THREE DECISIONS WORTH READING BEFORE THE CODE
---------------------------------------------

1. THE SIX COMPONENTS ARE STORED, NOT JUST THE SCORE. The app's weight sliders
   recompute the score from these columns in the browser. That is the only way
   a slider can be honest: if the page stored a score it would have to
   re-aggregate raw records to move it, and arch §4.2 forbids the app
   aggregating anything. Store the parts, let the reader re-weight them.

2. EVERY COMPONENT IS SCALED TO [0,1]. Weights are only comparable if the
   things they multiply are. An unscaled `prevalence` of 0.24 beside a
   `defer_share` of 0.81 would make w3 look three times as influential as w1
   at equal weight — the sensitivity panel would then be measuring the scaling,
   not the ranking.

3. DEFAULT WEIGHTS ARE EQUAL. Not because equal weighting is right, but
   because any other default would be an assertion this evidence cannot
   support, and the whole point of S3-MET-2 is that the ranking must survive
   the reader disagreeing with the defaults. The Monte Carlo is run around
   them; if the top rank only holds at the defaults, that is the finding.

WHAT IS EXCLUDED, AND WHY IT IS SIZED FIRST (AC-12 / EC-INS-3)
--------------------------------------------------------------
C9 (intent was never live) and segment ① Collectors are not barriers — they are
correct behaviour. Leaving them in the denominator inflates the addressable
opportunity, which is the easiest way to produce a wrong answer that survives
casual review. But dropping them silently loses a real finding: if a fifth of
wishlisting carries no purchase intent, "much wishlisting is not intent" IS the
headline (EC-INS-3). So both are counted into `analysis_addressable` first and
removed second.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import codebook as cbm, db as dbm, runs as rmod  # noqa: E402

MIN_N_RANKED = 30      # AR-12 / arch §9.4 — below this, scored but never ranked
MIN_N_VISIBLE = 15
TARGET_SEGMENT_DEFAULT = 4          # Stuck Deciders (framework v2)
COLLECTORS_SEGMENT = 1              # ① Collectors — the S3 'bookmarker' population
NON_ADDRESSABLE_CODES = {"C9"}      # framework C10: intent never existed
RESIDUAL_CODES = {"Z-99"}           # not a barrier; a measure of codebook fit

COMPONENTS = ("prevalence", "intensity", "defer_share",
              "solvable_without_money", "evidence_strength", "segment_fit")
DEFAULT_WEIGHTS = {c: 1.0 for c in COMPONENTS}

SOLVABILITY = {True: 1.0, "yes": 1.0, "partly": 0.5, False: 0.0, "no": 0.0, "na": 0.0}

SENSITIVITY_DRAWS = 1000
SENSITIVITY_PERTURBATION = 0.30     # ±30%, per evals.md S3-MET-2
SEED = 20260820
FRAGILE_INVERSION = 3.0             # <= 3x under-reporting is plausible for a silent barrier


# --------------------------------------------------------------- loading
def _load(con) -> dict:
    """Everything the scorer needs, read once. Exclusions honoured — a mark
    nothing reads is worse than no mark (see crosstabs._load)."""
    recs = {r["record_id"]: dict(r) for r in con.execute("""
        SELECT rec.record_id, rec.source, rec.author_hash, v.secondhand, v.myntra_specific
        FROM relevance v JOIN records rec ON rec.record_id = v.record_id
        WHERE v.is_relevant = 1
          AND NOT EXISTS (SELECT 1 FROM exclusions e WHERE e.record_id = rec.record_id)""")}

    codes = defaultdict(set)
    for r in con.execute("SELECT record_id, code FROM classifications"):
        if r["record_id"] in recs:
            codes[r["record_id"]].add(r["code"])

    meta = {r["record_id"]: dict(r) for r in con.execute(
        "SELECT record_id, outcome, intensity, workaround, workaround_effort,"
        " counterfactual FROM record_meta")}

    seg = {r["record_id"]: (int(r["segment_id"]), r["segment_name"])
           for r in con.execute("SELECT record_id, segment_id, segment_name FROM segments_v2")}

    strength = {r["code"]: float(r["composite"]) for r in con.execute(
        "SELECT code, composite FROM analysis_evidence_strength")}

    return {"recs": recs, "codes": codes, "meta": meta, "seg": seg, "strength": strength}


# ------------------------------------------------- addressable population
def size_and_exclude(con, data: dict, run_id: str) -> tuple[set[str], list[dict]]:
    """AC-12. Count the non-addressable populations, write the sizes, THEN drop
    them. Returns (addressable record ids, buckets written)."""
    recs, codes, seg = data["recs"], data["codes"], data["seg"]
    corpus = set(recs)

    c9 = {r for r in corpus if codes.get(r, set()) & NON_ADDRESSABLE_CODES}
    collectors = {r for r in corpus if seg.get(r, (None, ""))[0] == COLLECTORS_SEGMENT}
    both = c9 & collectors
    addressable = corpus - c9 - collectors

    n = len(corpus)
    buckets = [
        {"bucket": "corpus", "label": "Relevant records after exclusions",
         "n": n, "share": 1.0, "excluded": 0,
         "reason": "the analysed corpus — the denominator every share on the Analysis page uses"},
        {"bucket": "c9_no_live_intent", "label": "C9 — intent was never live (framework C10)",
         "n": len(c9), "share": len(c9) / n, "excluded": 1,
         "reason": "AC-12 / EC-INS-3: no purchase intent to convert. Sized because its SIZE is "
                   "the finding — this is how much wishlisting is not intent — then removed so "
                   "it cannot inflate the addressable opportunity"},
        {"bucket": "collectors", "label": "Segment ① Collectors — saving as a taste archive",
         "n": len(collectors), "share": len(collectors) / n, "excluded": 1,
         "reason": "AC-12: the framework-v2 successor to segment S3 (bookmarkers). Correct "
                   "behaviour, not a barrier; addressing it would be optimising against the user"},
        {"bucket": "overlap", "label": "Counted in both exclusions",
         "n": len(both), "share": len(both) / n, "excluded": 1,
         "reason": "reported so the two exclusions above are not read as additive"},
        {"bucket": "addressable", "label": "Addressable population",
         "n": len(addressable), "share": len(addressable) / n, "excluded": 0,
         "reason": "corpus minus the union of the two non-addressable populations. Every "
                   "opportunity share below is computed against THIS denominator"},
    ]
    for b in buckets:
        con.execute(
            "INSERT OR REPLACE INTO analysis_addressable (bucket, label, n, share_of_corpus,"
            " excluded, reason, run_id) VALUES (?,?,?,?,?,?,?)",
            (b["bucket"], b["label"], b["n"], b["share"], b["excluded"], b["reason"], run_id))
    return addressable, buckets


# ------------------------------------------------------------ components
def components(data: dict, pop: set[str], cb, target_segment: int) -> dict[str, dict]:
    """The six inputs per code, each on [0,1]. No weighting happens here."""
    recs, codes, meta, seg, strength = (
        data["recs"], data["codes"], data["meta"], data["seg"], data["strength"])
    denom = len(pop)
    by_code: dict[str, list[str]] = defaultdict(list)
    for r in pop:
        for c in codes.get(r, ()):
            by_code[c].append(r)

    base_target = sum(1 for r in pop if seg.get(r, (None, ""))[0] == target_segment) / denom

    raw: dict[str, dict] = {}
    for cid, spec in cb.codes.items():
        ids = by_code.get(cid, [])
        n = len(ids)
        m = [meta.get(i, {}) for i in ids]

        # Expressed intensity (1-5) and workaround effort are different
        # evidence of the same thing. A barrier people merely voice loudly is
        # weaker than one they build a workaround around — a workaround PROVES
        # the unmet need without being asked (§5.2) — so both enter, equally.
        voiced = [x["intensity"] for x in m if x.get("intensity")]
        voiced_n = ((sum(voiced) / len(voiced)) - 1) / 4 if voiced else 0.0
        # secondhand records are excluded from workaround evidence (EC-REL-4):
        # an opinion about other people's workarounds is not evidence of one.
        own = [i for i in ids if not recs[i]["secondhand"]]
        wk = [meta.get(i, {}) for i in own if meta.get(i, {}).get("workaround")]
        effort = [x.get("workaround_effort") or 0 for x in wk]
        wk_index = ((sum(effort) / len(effort)) / 3) * (len(wk) / len(own)) if wk and own else 0.0

        outcomes = [x.get("outcome") for x in m if x.get("outcome") in ("defer", "exit")]
        defer = sum(1 for o in outcomes if o == "defer") / len(outcomes) if outcomes else 0.0

        in_target = sum(1 for i in ids if seg.get(i, (None, ""))[0] == target_segment)
        lift = (in_target / n) / base_target if n and base_target else 0.0

        raw[cid] = {
            "stage": spec["stage"],
            "n": n,
            "n_authors": len({recs[i]["author_hash"] for i in ids if recs[i]["author_hash"]}),
            "share": n / denom,
            "prevalence_raw": n / denom,
            "intensity_raw": 0.5 * voiced_n + 0.5 * wk_index,
            "defer_share": defer,
            "solvable_without_money": SOLVABILITY.get(spec["solvable_without_money"], 0.0),
            "evidence_strength": strength.get(cid, 0.0),
            # Lift, not share: a code held by 40% of the target segment but 40%
            # of everyone is not a reason to pick that segment. Capped at 2x —
            # beyond that the cell is thin and the ratio is noise, and an
            # uncapped lift would let one n=15 cell dominate the ranking.
            #
            # PARTLY CIRCULAR, AND THAT MUST TRAVEL WITH THE NUMBER. Segment 4
            # is DERIVED as "intent + near horizon + not decided", and "not
            # decided" is operationalised as the presence of a Confidence-phase
            # code (segments.py Q3). So every Confidence code is barred from
            # segments 1, 3 and 5 by definition, and its lift into segment 4 is
            # inflated by the derivation rule rather than measured against it.
            # C10 sits at 2.18x for exactly this reason. The component is kept
            # because relative lift WITHIN the confidence codes is still
            # informative, but `leave_one_out()` reports the ranking with this
            # weight at zero, and the app's w6 slider goes to 0 for the same
            # reason. A number that is partly definitional is usable; a number
            # that is partly definitional and presented as empirical is not.
            "segment_fit_raw": min(lift, 2.0) / 2.0,
            "target_lift": lift if n else None,
        }

    # Scale the two unbounded components against the strongest code, so all six
    # land on [0,1] and the weights mean what the slider says they mean.
    for key, out in (("prevalence_raw", "prevalence"), ("intensity_raw", "intensity")):
        top = max((v[key] for v in raw.values()), default=0.0)
        for v in raw.values():
            v[out] = (v[key] / top) if top else 0.0
    for v in raw.values():
        v["segment_fit"] = v["segment_fit_raw"]
    return raw


def score_of(comp: dict, weights: dict[str, float]) -> float:
    total = sum(weights.values())
    if total <= 0:
        return 0.0
    return sum(weights[c] * comp[c] for c in COMPONENTS) / total


# ------------------------------------------------------------ sensitivity
def sensitivity(rows: list[dict], *, draws: int = SENSITIVITY_DRAWS,
                perturbation: float = SENSITIVITY_PERTURBATION,
                seed: int = SEED) -> list[dict]:
    """S3-MET-2. Perturb all six weights ±`perturbation`, `draws` times, and
    report how often each code holds the top rank.

    This is the answer to "why those weights?" — given BEFORE it is asked. A
    code that leads 87% of plausible weightings is a claim; one that leads 45%
    means the top two cannot be separated on this evidence, and the honest
    headline is that the interviews are the tiebreak rather than a formality
    (evals.md §S3-MET-2).
    """
    import random

    rng = random.Random(seed)
    eligible = [r for r in rows if r["rank"] is not None]
    if len(eligible) < 2:
        return []
    tops: dict[str, int] = defaultdict(int)
    top3: dict[str, int] = defaultdict(int)
    ranks: dict[str, list[int]] = defaultdict(list)

    for _ in range(draws):
        w = {c: DEFAULT_WEIGHTS[c] * (1 + rng.uniform(-perturbation, perturbation))
             for c in COMPONENTS}
        order = sorted(eligible, key=lambda r: -score_of(r, w))
        tops[order[0]["code"]] += 1
        for r in order[:3]:
            top3[r["code"]] += 1
        for i, r in enumerate(order, 1):
            ranks[r["code"]].append(i)

    out = []
    for r in eligible:
        rs = sorted(ranks[r["code"]])
        out.append({
            "code": r["code"],
            "top_share": tops[r["code"]] / draws,
            "top3_share": top3[r["code"]] / draws,
            "mean_rank": sum(rs) / len(rs),
            "p05_rank": rs[int(0.05 * len(rs))],
            "p95_rank": rs[min(int(0.95 * len(rs)), len(rs) - 1)],
            "n_draws": draws, "perturbation": perturbation, "seed": seed,
        })
    return sorted(out, key=lambda d: -d["top_share"])


def leave_one_out(rows: list[dict]) -> list[dict]:
    """The ranking with each component's weight set to zero, in turn.

    The Monte Carlo perturbs all six weights together and answers "is the top
    rank stable under disagreement about emphasis". It cannot answer "is the
    top rank an artefact of ONE component" — a component that is partly
    definitional, such as `segment_fit`, survives a +/-30% wobble untouched
    while being the whole reason a code leads. Zeroing one weight at a time is
    the check that catches that, and it is cheap.
    """
    eligible = [r for r in rows if r["rank"] is not None]
    if len(eligible) < 2:
        return []
    out = []
    for dropped in COMPONENTS:
        w = {c: (0.0 if c == dropped else 1.0) for c in COMPONENTS}
        order = sorted(eligible, key=lambda r: -score_of(r, w))
        out.append({"dropped": dropped,
                    "top": order[0]["code"],
                    "top3": [r["code"] for r in order[:3]],
                    "changes_top": order[0]["code"] != eligible[0]["code"]
                    if eligible[0]["rank"] == 1 else None})
    return out


# -------------------------------------------------------- stage inversion
def stage_inversion(data: dict, pop: set[str], cb) -> list[dict]:
    """S3-MET-3 / arch §7.3 — the 'what would you need to believe' number.

    `problemstatement.md` §8 establishes that the corpus structurally
    under-detects Stage A: forgetting produces no complaint, so a low A-count
    is not evidence that A is small. Rather than accept the ranking or discard
    it, compute how far each stage would have to be under-reported to overtake
    the leader. 3x is plausible for a silent barrier and makes the conclusion
    fragile; 40x makes it safe. Either way it is a number, not an adjective.
    """
    codes = data["codes"]
    per_stage: dict[str, set[str]] = defaultdict(set)
    for r in pop:
        for c in codes.get(r, ()):
            spec = cb.codes.get(c)
            if spec and spec["stage"] in ("A", "B", "C", "D"):
                per_stage[spec["stage"]].add(r)

    counts = {s: len(v) for s, v in per_stage.items()}
    if not counts:
        return []
    leader = max(counts, key=lambda s: counts[s])
    n_lead = counts[leader]
    out = []
    for stage in sorted(counts):
        n = counts[stage]
        factor = None if stage == leader else (n_lead / n if n else math.inf)
        out.append({
            "stage": stage, "n": n, "share": n / len(pop),
            "leader": leader, "leader_n": n_lead,
            "inversion_factor": factor,
            "fragile": int(factor is not None and factor <= FRAGILE_INVERSION),
        })
    return out


# --------------------------------------------------- segment recommendation
def segment_recommendation(con, data: dict, pop: set[str], cb,
                           comps: dict[str, dict], run_id: str) -> list[dict]:
    """AC-12 with the EC-INS-8 fallback made explicit.

    segment x code is the recommendation we want; at this corpus size most
    cells fall below a readable n, which arch §9.4 anticipated. The fallback to
    segment x stage is pre-planned, not improvised — and WHICH matrix carried
    the decision is stored in `basis`, so a directional read cannot later be
    quoted as a ranked one.
    """
    codes, seg, meta = data["codes"], data["seg"], data["meta"]
    denom = len(pop)
    members: dict[int, list[str]] = defaultdict(list)
    names: dict[int, str] = {}
    for r in pop:
        sid, sname = seg.get(r, (0, "unlabelled"))
        members[sid].append(r)
        names[sid] = sname

    base = {cid: comps[cid]["share"] for cid in comps}
    rows = []
    for sid, ids in sorted(members.items()):
        n = len(ids)
        cell: dict[str, int] = defaultdict(int)
        for r in ids:
            for c in codes.get(r, ()):
                if c not in RESIDUAL_CODES:
                    cell[c] += 1
        rankable = sum(1 for v in cell.values() if v >= MIN_N_RANKED)
        basis = "segment x code" if rankable >= 3 else "segment x stage"

        top = sorted(cell.items(), key=lambda kv: -kv[1])[:6]
        top_codes = [{"code": c, "n": v, "share": v / n,
                      "lift": (v / n) / base[c] if base.get(c) else None} for c, v in top]
        distinctive = sorted(
            [t for t in top_codes if t["n"] >= MIN_N_VISIBLE and t["lift"]],
            key=lambda t: -t["lift"])[:3]

        # Solvable without money is the binding constraint C-2: a large segment
        # whose barriers all need a discount is not an opportunity this project
        # is allowed to take.
        solvable_n = sum(v for c, v in cell.items()
                         if SOLVABILITY.get(cb.codes[c]["solvable_without_money"], 0.0) >= 0.5)
        defer_n = sum(1 for r in ids if (meta.get(r) or {}).get("outcome") == "defer")

        solvable_term = solvable_n / sum(cell.values()) if cell else 0.0
        defer_term = defer_n / n if n else 0.0
        distinct_term = min(max((t["lift"] for t in distinctive), default=0.0), 2.0) / 2.0
        score = (0.30 * (n / max(len(v) for v in members.values()))
                 + 0.25 * solvable_term + 0.25 * defer_term + 0.20 * distinct_term)

        rows.append({
            "segment_id": sid, "segment_name": names[sid], "n": n, "share": n / denom,
            "basis": basis, "rankable_cells": rankable,
            "addressable_n": n, "solvable_n": solvable_n,
            "top_codes": top_codes, "distinctive": distinctive, "score": score,
            "solvable_share": solvable_term, "n_code_rows": sum(cell.values()),
        })

    # Collectors and anything with no live intent were already removed from
    # `pop`, so whatever leads here is addressable by construction.
    best = max(rows, key=lambda r: r["score"]) if rows else None
    for r in rows:
        r["recommended"] = int(best is not None and r["segment_id"] == best["segment_id"])
        d = r["distinctive"][0] if r["distinctive"] else None
        r["rationale"] = (
            f"{r['n']:,} records ({r['share']:.1%} of the addressable population); "
            f"{r['solvable_share']:.0%} of its coded "
            f"barriers are solvable without a monetary incentive; "
            + (f"most distinctive barrier {d['code']} at {d['lift']:.2f}x the corpus rate"
               if d else "no barrier reaches the visibility floor at this n")
            + f". Basis: {r['basis']}"
            + ("" if r["basis"] == "segment x code"
               else f" — only {r['rankable_cells']} code cells reach n>={MIN_N_RANKED}, "
                    "so code-level detail here is directional (EC-INS-8)"))
        con.execute(
            "INSERT OR REPLACE INTO analysis_segment_recommendation (segment_id, segment_name,"
            " n, share, basis, rankable_cells, addressable_n, solvable_n, top_codes,"
            " distinctive, score, recommended, rationale, run_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["segment_id"], r["segment_name"], r["n"], r["share"], r["basis"],
             r["rankable_cells"], r["addressable_n"], r["solvable_n"],
             json.dumps(r["top_codes"]), json.dumps(r["distinctive"]), r["score"],
             r["recommended"], r["rationale"], run_id))
    return rows


# ------------------------------------------------------------------- run
def run(con, *, target_segment: int = TARGET_SEGMENT_DEFAULT) -> dict:
    cb = cbm.load()
    data = _load(con)
    if not data["recs"]:
        return {"error": "no relevant records"}

    with rmod.Run(con, "opportunity", model=None, codebook_version=cb.version_string,
                  weights=DEFAULT_WEIGHTS, target_segment=target_segment,
                  draws=SENSITIVITY_DRAWS, perturbation=SENSITIVITY_PERTURBATION,
                  seed=SEED) as R:
        rid = R.run_id
        for t in ("analysis_opportunity", "analysis_addressable",
                  "analysis_weight_sensitivity", "analysis_stage_inversion",
                  "analysis_segment_recommendation"):
            con.execute(f"DELETE FROM {t}")

        pop, buckets = size_and_exclude(con, data, rid)
        R.n_input = len(pop)
        comps = components(data, pop, cb, target_segment)

        rows = []
        for cid, c in comps.items():
            excluded, reason = 0, None
            if cid in NON_ADDRESSABLE_CODES:
                excluded, reason = 1, ("AC-12: intent was never live — nothing to convert. "
                                       "Sized in analysis_addressable, then excluded")
            elif cid in RESIDUAL_CODES:
                excluded, reason = 1, ("residual bucket: a measure of codebook fit, "
                                       "not a barrier that can be solved")
            elif c["n"] < MIN_N_RANKED:
                excluded, reason = 0, (f"scored but not ranked — n={c['n']} is below the "
                                       f"n>={MIN_N_RANKED} floor for a ranked claim (AR-12)")
            rows.append({**c, "code": cid, "excluded": excluded, "exclusion_reason": reason,
                         "score": score_of(c, DEFAULT_WEIGHTS)})

        rankable = [r for r in rows if not r["excluded"] and r["n"] >= MIN_N_RANKED]
        for r in rows:
            r["rank"] = None
        for i, r in enumerate(sorted(rankable, key=lambda r: -r["score"]), 1):
            r["rank"] = i

        for r in rows:
            con.execute(
                "INSERT OR REPLACE INTO analysis_opportunity (code, stage, prevalence,"
                " intensity, defer_share, solvable_without_money, evidence_strength,"
                " segment_fit, score, rank, n, excluded, exclusion_reason, run_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["code"], r["stage"], r["prevalence"], r["intensity"], r["defer_share"],
                 r["solvable_without_money"], r["evidence_strength"], r["segment_fit"],
                 r["score"], r["rank"], r["n"], r["excluded"], r["exclusion_reason"], rid))

        for s in sensitivity(rows):
            con.execute(
                "INSERT OR REPLACE INTO analysis_weight_sensitivity (code, top_share,"
                " top3_share, mean_rank, p05_rank, p95_rank, n_draws, perturbation, seed,"
                " run_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (s["code"], s["top_share"], s["top3_share"], s["mean_rank"], s["p05_rank"],
                 s["p95_rank"], s["n_draws"], s["perturbation"], s["seed"], rid))

        inversions = stage_inversion(data, pop, cb)
        for iv in inversions:
            con.execute(
                "INSERT OR REPLACE INTO analysis_stage_inversion (stage, n, share, leader,"
                " leader_n, inversion_factor, fragile, run_id) VALUES (?,?,?,?,?,?,?,?)",
                (iv["stage"], iv["n"], iv["share"], iv["leader"], iv["leader_n"],
                 iv["inversion_factor"], iv["fragile"], rid))

        segs = segment_recommendation(con, data, pop, cb, comps, rid)
        con.commit()
        R.n_output = len(rows)

    return {"run_id": rid, "addressable": len(pop), "buckets": buckets,
            "ranked": len(rankable), "inversions": inversions,
            "leave_one_out": leave_one_out(rows),
            "recommended_segment": next((s for s in segs if s["recommended"]), None)}


if __name__ == "__main__":
    con = dbm.connect()
    out = run(con)
    print(f"run_id            {out['run_id']}")
    print(f"addressable pop   {out['addressable']:,}   ranked codes {out['ranked']}")
    print("\naddressable sizing (AC-12)")
    for b in out["buckets"]:
        print(f"  {b['bucket']:<20} n={b['n']:>5}  {b['share']:>6.1%}  "
              f"{'EXCLUDED' if b['excluded'] else ''}")
    print("\nopportunity ranking")
    for r in con.execute("SELECT code, stage, rank, round(score,4) s, n FROM analysis_opportunity"
                         " WHERE rank IS NOT NULL ORDER BY rank"):
        print(f"  #{r['rank']:<2} {r['code']:<6} {r['stage']}  score {r['s']:.4f}  n={r['n']}")
    print("\nweight robustness (1,000 draws, +/-30%)")
    for r in con.execute("SELECT code, round(top_share,3) t, round(mean_rank,2) m, p05_rank,"
                         " p95_rank FROM analysis_weight_sensitivity ORDER BY t DESC LIMIT 6"):
        print(f"  {r['code']:<6} top {r['t']:>6.1%}   mean rank {r['m']:.2f}  "
              f"[{r['p05_rank']}–{r['p95_rank']}]")
    print("\nranking with each component dropped in turn")
    for lo in out["leave_one_out"]:
        print(f"  drop {lo['dropped']:<24} top -> {lo['top']:<6} "
              f"top3 {' '.join(lo['top3'])}")
    print("\nstage inversion (S3-MET-3)")
    for iv in out["inversions"]:
        f = iv["inversion_factor"]
        print(f"  stage {iv['stage']}  n={iv['n']:>4}  " +
              ("LEADER" if f is None else
               f"would need {f:.1f}x under-reporting to overtake {iv['leader']}"
               f"{'   ← FRAGILE' if iv['fragile'] else ''}"))
    rec = out["recommended_segment"]
    if rec:
        print(f"\nsegment recommendation: ({rec['segment_id']}) {rec['segment_name']}")
        print(f"  {rec['rationale']}")
