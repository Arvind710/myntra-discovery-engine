"""Materialise the analysis_* tables (arch §4.2, FR-5.5).

DESIGN RULE: the app performs NO aggregation over raw records. Everything
it displays is a SELECT from one of these tables. That is what guarantees
the charts and the chatbot cannot disagree -- they read the same rows.

Every table carries `n` and `run_id` (S2-INV-9), and every count is
accompanied by a DISTINCT-AUTHOR count (EC-COL-9): 200 records from 12
authors is a weaker claim than 200 from 180, and only one of those numbers
survives contact with a sceptical reader.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import codebook as cbm, db as dbm, runs as rmod  # noqa: E402

MIN_N_RANKED = 30   # AR-12 / arch §9.4
MIN_N_VISIBLE = 15


def _load(con):
    """Relevant records with their codes and metadata."""
    # `exclusions` is a marking table ([A.1]) and analysis is supposed to take
    # its denominator from what survives it. This query previously read
    # `relevance` directly, so ANY exclusion written after the relevance pass
    # was silently ignored — the mark was recorded, the analysis kept using the
    # record, and nothing anywhere disagreed. Found when excluding the
    # low-yield subreddits; it would have applied to every future exclusion too.
    recs = {r["record_id"]: dict(r) for r in con.execute("""
        SELECT rec.record_id, rec.source, rec.author_hash, rec.created_at,
               v.secondhand, v.myntra_specific
        FROM relevance v JOIN records rec ON rec.record_id = v.record_id
        WHERE v.is_relevant = 1
          AND NOT EXISTS (SELECT 1 FROM exclusions e
                          WHERE e.record_id = rec.record_id)""")}
    codes = defaultdict(list)
    for r in con.execute("SELECT record_id, code, confidence, is_blocking FROM classifications"):
        if r["record_id"] in recs:
            codes[r["record_id"]].append(dict(r))
    meta = {r["record_id"]: dict(r) for r in con.execute("SELECT * FROM record_meta")}
    return recs, codes, meta


def run(con) -> dict:
    cb = cbm.load()
    recs, codes, meta = _load(con)
    denom = len(recs)
    if not denom:
        return {"denominator": 0}

    with rmod.Run(con, "crosstabs", model=None, codebook_version=cb.version_string) as R:
        rid = R.run_id
        R.n_input = denom
        for t in ("analysis_code_prevalence", "analysis_segment_code", "analysis_cooccurrence",
                  "analysis_source_code", "analysis_stage_outcome", "analysis_workaround",
                  "analysis_counterfactuals", "analysis_evidence_strength",
                  "analysis_subcode"):
            con.execute(f"DELETE FROM {t}")

        # ---- code prevalence -----------------------------------------
        # AC-10: ALL 33 codes appear, including zero-count ones. A code with
        # no evidence is a reportable result; a code never CHECKED is a hole.
        by_code: dict[str, list[str]] = defaultdict(list)
        for r, cs in codes.items():
            for c in cs:
                by_code[c["code"]].append(r)

        for cid in list(cb.codes):
            ids = by_code.get(cid, [])
            n = len(ids)
            authors = len({recs[i]["author_hash"] for i in ids if recs[i]["author_hash"]})
            srcs = len({recs[i]["source"] for i in ids})
            d = cb.codes[cid]
            conf = [c["confidence"] for i in ids for c in codes[i] if c["code"] == cid]
            con.execute(
                "INSERT INTO analysis_code_prevalence (code, stage, phase, outcome, n,"
                " n_distinct_authors, denominator, share, n_sources, mean_confidence,"
                " below_min_n, run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, d["stage"], d["phase"], d["outcome_default"], n, authors, denom,
                 n / denom, srcs, sum(conf) / len(conf) if conf else None,
                 int(n < MIN_N_RANKED), rid))

        # ---- code x source, with Jensen-Shannon divergence -------------
        # Separates real signal from platform demographics: a high JS means
        # the code may be an artefact of who posts there (§8).
        pooled = {c: len(v) / denom for c, v in by_code.items()}
        for src in {r["source"] for r in recs.values()}:
            sids = [i for i, r in recs.items() if r["source"] == src]
            sdenom = len(sids)
            sdist = {}
            for cid in cb.codes:
                n = len([i for i in by_code.get(cid, []) if recs[i]["source"] == src])
                sdist[cid] = n / sdenom if sdenom else 0
            js = 0.0
            for cid in cb.codes:
                p, q = sdist.get(cid, 0), pooled.get(cid, 0)
                m = (p + q) / 2
                if p > 0 and m > 0:
                    js += 0.5 * p * math.log2(p / m)
                if q > 0 and m > 0:
                    js += 0.5 * q * math.log2(q / m)
            for cid in cb.codes:
                ids = [i for i in by_code.get(cid, []) if recs[i]["source"] == src]
                if not ids:
                    continue
                auth = len({recs[i]["author_hash"] for i in ids if recs[i]["author_hash"]})
                con.execute(
                    "INSERT INTO analysis_source_code (source, code, n, n_distinct_authors,"
                    " denominator, share, js_divergence, run_id) VALUES (?,?,?,?,?,?,?,?)",
                    (src, cid, len(ids), auth, sdenom, len(ids) / sdenom, js, rid))

        # ---- segment x code ------------------------------------------
        # Coverage is STORED, not inferred at render (S2-INV-10). The app
        # never shows a segment breakdown without it.
        labelled = [i for i in recs if meta.get(i, {}).get("segment") not in (None, "unknown")]
        coverage = len(labelled) / denom
        seg_ids = defaultdict(list)
        for i in recs:
            seg_ids[meta.get(i, {}).get("segment") or "unknown"].append(i)
        for seg, ids in seg_ids.items():
            for cid in cb.codes:
                hit = [i for i in ids if any(c["code"] == cid for c in codes.get(i, []))]
                if not hit:
                    continue
                auth = len({recs[i]["author_hash"] for i in hit if recs[i]["author_hash"]})
                con.execute(
                    "INSERT INTO analysis_segment_code (segment, code, n, n_distinct_authors,"
                    " denominator, share, coverage, below_min_n, run_id)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (seg, cid, len(hit), auth, len(ids), len(hit) / len(ids),
                     coverage, int(len(hit) < MIN_N_VISIBLE), rid))

        # ---- co-occurrence with lift and PMI --------------------------
        # Lift surfaces SURPRISING pairings, not frequent ones: C1xC7 at lift
        # 3.2 means fit doubt and return friction are one compound problem,
        # not two independent ones.
        ids_by_code = {c: set(v) for c, v in by_code.items()}
        keys = sorted(ids_by_code)
        for a_i, a in enumerate(keys):
            for b in keys[a_i + 1:]:
                joint = ids_by_code[a] & ids_by_code[b]
                if not joint:
                    continue
                na, nb, nj = len(ids_by_code[a]), len(ids_by_code[b]), len(joint)
                pa, pb, pj = na / denom, nb / denom, nj / denom
                lift = pj / (pa * pb) if pa and pb else None
                con.execute(
                    "INSERT INTO analysis_cooccurrence (code_a, code_b, n_joint, n_a, n_b,"
                    " denominator, lift, pmi, min_support_met, run_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (a, b, nj, na, nb, denom, lift,
                     math.log2(lift) if lift and lift > 0 else None,
                     int(nj >= MIN_N_VISIBLE), rid))

        # ---- stage x outcome -----------------------------------------
        # Defer is the WINNABLE population; Exit mostly is not.
        so = defaultdict(int)
        for i in recs:
            m = meta.get(i, {})
            for s in {cb.codes[c["code"]]["stage"] for c in codes.get(i, []) if c["code"] in cb.codes}:
                so[(s, m.get("outcome") or "na")] += 1
        for (s, o), n in so.items():
            con.execute(
                "INSERT INTO analysis_stage_outcome (stage, outcome, n, denominator, share, run_id)"
                " VALUES (?,?,?,?,?,?)", (s, o, n, denom, n / denom, rid))

        # ---- workarounds and counterfactuals --------------------------
        # Effort spent proves unmet need better than complaint volume. A quiet
        # barrier people work around hard beats a loud one they merely grumble
        # about. secondhand records are EXCLUDED (EC-REL-4): an opinion about
        # other people's workarounds is not evidence of one.
        for cid, ids in by_code.items():
            own = [i for i in ids if not recs[i]["secondhand"]]
            if not own:
                continue
            wk = [i for i in own if meta.get(i, {}).get("workaround")]
            eff = [meta[i].get("workaround_effort") or 0 for i in wk]
            share = len(wk) / len(own)
            con.execute(
                "INSERT INTO analysis_workaround (code, n_with_workaround, n_code, share,"
                " mean_effort, intensity_index, run_id) VALUES (?,?,?,?,?,?,?)",
                (cid, len(wk), len(own), share,
                 sum(eff) / len(eff) if eff else None,
                 (sum(eff) / len(eff) * share) if eff else None, rid))

            cf = [i for i in own if meta.get(i, {}).get("counterfactual")]
            con.execute(
                "INSERT INTO analysis_counterfactuals (code, n_counterfactual, n_code, share,"
                " exemplar_ids, run_id) VALUES (?,?,?,?,?,?)",
                (cid, len(cf), len(own), len(cf) / len(own), ",".join(cf[:5]), rid))

        # ---- evidence strength ----------------------------------------
        # Downgrades a code carried by one source; upgrades one corroborated
        # across four. Transferability (codebook v1.2) enters here: a
        # low-transferability code is scored on its MYNTRA-SPECIFIC n.
        n_src = len({r["source"] for r in recs.values()})
        for cid in cb.codes:
            ids = by_code.get(cid, [])
            if not ids:
                continue
            d = cb.codes[cid]
            eff_ids = ([i for i in ids if recs[i]["myntra_specific"]]
                       if d.get("transferability") == "low" else ids)
            n = len(eff_ids)
            srcs = len({recs[i]["source"] for i in eff_ids})
            conf = [c["confidence"] for i in eff_ids for c in codes[i] if c["code"] == cid]
            wk = len([i for i in eff_ids if meta.get(i, {}).get("workaround")])
            cf = len([i for i in eff_ids if meta.get(i, {}).get("counterfactual")])
            prev = n / denom
            div = srcs / n_src if n_src else 0
            mc = sum(conf) / len(conf) if conf else 0
            composite = (0.30 * min(prev * 10, 1) + 0.25 * div + 0.15 * (cf / n if n else 0)
                         + 0.15 * (wk / n if n else 0) + 0.15 * mc)
            con.execute(
                "INSERT INTO analysis_evidence_strength (code, prevalence, source_diversity,"
                " counterfactual_rate, workaround_rate, mean_confidence, recency, composite,"
                " n, run_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (cid, prev, div, cf / n if n else 0, wk / n if n else 0, mc, None,
                 composite, n, rid))

        # ---- sub-code roll-up ----------------------------------------
        # A theme's headline number does not say what to build; the sub-code
        # does. C2 at 24% is "photos mislead"; C2.4 at 72% OF C2 is "is this
        # worth the price" — a pricing-transparency problem wearing a quality
        # complaint's clothes. Rolled up here so it is a citable row rather
        # than an aggregation performed at render time.
        #
        # Sub-coding ran twice for C2 and C3 (a re-run after a prompt fix), and
        # `subcodes` keys on run_id, so a naive GROUP BY counted the same
        # record under both runs and produced a 120% share. Take the LATEST run
        # PER THEME — a theme's two runs used different populations, so mixing
        # them is not a smaller version of the same error, it is two different
        # analyses added together.
        latest = {r["theme"]: r["run_id"] for r in con.execute(
            "SELECT theme, run_id, max(rowid) FROM subcodes GROUP BY theme")}
        sub = defaultdict(lambda: defaultdict(list))
        seen: set[tuple[str, str, str]] = set()
        for r in con.execute("SELECT record_id, theme, subcode, confidence, run_id FROM subcodes"):
            key = (r["record_id"], r["theme"], r["subcode"])
            if (r["record_id"] in recs and latest.get(r["theme"]) == r["run_id"]
                    and key not in seen):
                seen.add(key)
                sub[r["theme"]][r["subcode"]].append(r["confidence"] or 0.0)
        for theme, kinds in sub.items():
            n_theme = len({i for i in recs
                           if any(c["code"] == theme for c in codes.get(i, []))})
            for scode, confs in kinds.items():
                con.execute(
                    "INSERT INTO analysis_subcode (theme, subcode, n, n_theme, share,"
                    " mean_confidence, below_min_n, run_id) VALUES (?,?,?,?,?,?,?,?)",
                    (theme, scode, len(confs), n_theme,
                     len(confs) / n_theme if n_theme else None,
                     sum(confs) / len(confs) if confs else None,
                     int(len(confs) < MIN_N_VISIBLE), rid))

        con.commit()
        R.n_output = denom
        return {"denominator": denom, "run_id": rid,
                "segment_coverage": coverage, "codes_present": len(by_code)}


if __name__ == "__main__":
    con = dbm.connect()
    out = run(con)
    print(out)
