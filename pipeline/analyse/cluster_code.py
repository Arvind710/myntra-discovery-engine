"""Track C — reconcile the inductive clusters against the deductive codes.

WHY THIS RUNS BEFORE THE NOVELTY CHECK
--------------------------------------
Track B (clustering) exists as the only protection against codebook blindness:
it finds what the corpus says without being told what to look for. That
protection is worth nothing until the clusters are placed BESIDE the codes,
because the interesting cases are structural, not textual:

  * a cluster that spreads evenly across many codes is a theme the codebook
    CUTS THROUGH — the codebook sees five barriers where users describe one
    situation;
  * a cluster that is almost entirely Z-99 is a theme the codebook MISSES;
  * a code scattered across many clusters is a code that names a category
    users do not experience as one thing.

`evals.md` S3-MET-1 says novelty usually hides here, so declaring AC-6 either
way without this table is declaring it without looking.

Both entropies are normalised to [0,1] so they can be read as "how spread".
0 = perfectly aligned (this cluster is one code), 1 = maximally spread.
Deterministic: no model call, no randomness.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm, runs as rmod  # noqa: E402


def _norm_entropy(counts: list[int]) -> float | None:
    """Shannon entropy over a distribution, divided by log2(k).

    Unnormalised entropy is not comparable between a cluster spread over 3
    codes and one spread over 12 — the second has a larger ceiling. Dividing
    by the ceiling is what makes "how spread is this" one number.
    """
    total = sum(counts)
    if total <= 0 or len(counts) < 2:
        return 0.0 if total > 0 else None
    h = -sum((c / total) * math.log2(c / total) for c in counts if c > 0)
    return h / math.log2(len(counts))


def run(con) -> dict:
    # Exclusions are honoured here for the same reason crosstabs honours them:
    # a cluster sized against 1,199 records beside a code sized against 1,018
    # is two numbers on one screen describing different corpora.
    live = {r[0] for r in con.execute("""
        SELECT rec.record_id FROM relevance v JOIN records rec ON rec.record_id = v.record_id
        WHERE v.is_relevant = 1
          AND NOT EXISTS (SELECT 1 FROM exclusions e WHERE e.record_id = rec.record_id)""")}

    codes_of = defaultdict(set)
    for rid, code in con.execute("SELECT record_id, code FROM classifications"):
        if rid in live:
            codes_of[rid].add(code)

    with rmod.Run(con, "cluster-code", model=None) as R:
        rid_run = R.run_id
        con.execute("DELETE FROM analysis_cluster_code")
        written = 0

        for space in ("all", "z99"):
            members = defaultdict(list)
            for rec, cid in con.execute(
                    "SELECT record_id, cluster_id FROM clusters WHERE space = ?", (space,)):
                if rec in live and cid >= 0:          # -1 is HDBSCAN noise, not a cluster
                    members[int(cid)].append(rec)
            if not members:
                continue

            code_size: dict[str, int] = defaultdict(int)
            code_clusters: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
            for cid, recs in members.items():
                for rec in recs:
                    for c in codes_of.get(rec, ()):
                        code_size[c] += 1
                        code_clusters[c][cid] += 1

            for cid, recs in sorted(members.items()):
                counts: dict[str, int] = defaultdict(int)
                for rec in recs:
                    for c in codes_of.get(rec, ()):
                        counts[c] += 1
                h_cluster = _norm_entropy(list(counts.values()))
                for code, n in sorted(counts.items(), key=lambda kv: -kv[1]):
                    con.execute(
                        "INSERT OR REPLACE INTO analysis_cluster_code (cluster_id, space, code,"
                        " n, cluster_size, code_size, entropy_code_to_cluster,"
                        " entropy_cluster_to_code, run_id) VALUES (?,?,?,?,?,?,?,?,?)",
                        (cid, space, code, n, len(recs), code_size[code],
                         _norm_entropy(list(code_clusters[code].values())), h_cluster, rid_run))
                    written += 1

        con.commit()
        R.n_input = len(live)
        R.n_output = written
        return {"run_id": rid_run, "rows": written, "records": len(live)}


if __name__ == "__main__":
    con = dbm.connect()
    print(run(con))
