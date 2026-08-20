"""S3-MET-1 / AC-6 — is any insight outside the pre-registered hypotheses?

AC-6 exists because a discovery engine that returns only its author's priors
did not mine the corpus; it confirmed a belief at some expense. The test is
therefore adversarial towards this project's own output.

SIMILARITY IS A FILTER, NOT A VERDICT (evals.md §S3-MET-1)
-----------------------------------------------------------
This module embeds every kept insight and all 28 reconstructed priors and
reports the maximum cosine similarity per insight. What it produces is a
SHORTLIST. Two sentences about different things share vocabulary; two sentences
about the same thing can be phrased apart. The score cannot tell those cases
apart and this file does not pretend otherwise — it prints the nearest prior
beside each insight so a person can read both and decide.

The by-hand verdict is written into `evals/reports/`, not computed here.

IF NOTHING CLEARS THE BAR (EC-INS-7)
-------------------------------------
Then check the Track B clusters and the cluster↔code reconciliation first,
because that is where novelty hides: those are the only views of the corpus not
shaped by the codebook. If it still clears nothing, the honest report is that
the corpus confirmed existing priors. Manufacturing a novel insight to satisfy
AC-6 is the worst available outcome — it is the confirmation theatre R-1 exists
to prevent, inverted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EMBED_MODEL = "text-embedding-3-small"

# THE THRESHOLD IS MEASURED, NOT CHOSEN
# --------------------------------------
# A hand-picked line produced a useless instrument: at 0.62 every insight was
# flagged novel, including one that merely restates the barrier ranking, and
# several were nearest to a prior about an unrelated code. A filter that fires
# on everything is not evidence of novelty — it is evidence the scale is wrong,
# and reporting 14 of 14 as novel would have been AC-6 satisfied by broken
# measurement, which is the EC-INS-7 failure wearing the opposite mask.
#
# So the line is calibrated against a CONTROL SET: one statement per
# well-evidenced code, written in the same quantified shape as a generated
# insight but saying only what the codebook already says. Those are non-novel
# by construction. An insight is a candidate only if it is LESS similar to the
# priors than almost any deliberate restatement is — the 5th percentile of the
# control distribution. That converts "is 0.62 the right number" into a
# measurement anyone can re-run.
CONTROL_QUANTILE = 0.05
FLAG_BELOW = None      # computed from the controls unless --threshold is given


def embed(client, texts: list[str], run) -> np.ndarray:
    r = client.embeddings.create(model=EMBED_MODEL, input=texts)
    run.add_usage(input_tokens=r.usage.total_tokens)
    X = np.array([d.embedding for d in r.data], dtype=np.float32)
    return X / np.linalg.norm(X, axis=1, keepdims=True)


def controls(con) -> list[str]:
    """Non-novel by construction: each names a code and restates what the
    codebook already claims about it, in the quantified shape the generator
    produces. Any of these that scored as novel would be a false positive, so
    their similarity distribution is the floor a real candidate must fall below.
    """
    import sys as _s
    _s.path.insert(0, str(ROOT))
    from pipeline.common import codebook as cbm
    cb = cbm.load()
    out = []
    for r in con.execute("SELECT code, n, share, n_distinct_authors FROM"
                         " analysis_code_prevalence WHERE n >= 30 ORDER BY n DESC"):
        d = cb.codes.get(r["code"])
        if not d:
            continue
        q = str(d.get("question") or "").strip().strip('"')
        out.append(
            f"{d['name']} is a leading barrier in the corpus: n={r['n']} records "
            f"({r['share']:.3f} share) from {r['n_distinct_authors']} distinct authors. "
            + (f"The unresolved question is: {q} " if q else "")
            + f"It sits at stage {d['stage']} and its default outcome is "
              f"{d['outcome_default']}.")
    return out


def apply_verdicts(con) -> int:
    """Write the by-hand AC-6 decision over the filter's shortlist.

    The filter cannot decide AC-6 and this is where the person's reading lands
    in the database. It refuses to run if the insights have been regenerated
    since the verdicts were written — a verdict attached to the wrong statement
    is worse than no verdict, because it looks like the judgement was made.
    """
    doc = yaml.safe_load((ROOT / "codebook" / "novelty_verdicts.yaml").read_text())
    rows = {r["insight_id"]: r["statement"] for r in con.execute(
        "SELECT insight_id, statement FROM insights")}
    verdicts = doc["verdicts"]

    missing = [v["id"] for v in verdicts if v["id"] not in rows]
    extra = [i for i in rows if i not in {v["id"] for v in verdicts}]
    if missing or extra:
        raise RuntimeError(
            "novelty_verdicts.yaml no longer matches the insights table"
            + (f" — verdicts for insights that do not exist: {missing}" if missing else "")
            + (f" — insights with no verdict: {extra}" if extra else "")
            + ". Re-read the candidates and rewrite the verdicts; do NOT carry them over.")

    def _norm(t: str) -> str:
        return "".join(ch for ch in t.lower().replace("\u2011", "-").replace("\u2010", "-")
                       if ch.isalnum() or ch == " ")

    drifted = [v["id"] for v in verdicts
               if not _norm(rows[v["id"]]).startswith(_norm(v["statement_prefix"]))]
    if drifted:
        raise RuntimeError(
            f"the statements behind {drifted} have changed since the verdicts were "
            "written — the insights were regenerated. Re-review them.")

    n_novel = 0
    for v in verdicts:
        con.execute("UPDATE insights SET novelty = ?, novelty_note = ? WHERE insight_id = ?",
                    (int(v["novel"]), " ".join(str(v["note"]).split()), v["id"]))
        n_novel += int(v["novel"])
    con.commit()
    print(f"applied {len(verdicts)} hand verdicts: {n_novel} confirmed novel "
          f"(AC-6 needs >= 1)")
    for v in verdicts:
        if v["novel"]:
            print(f"  {v['id']}{'  ** HEADLINE **' if v.get('headline') else ''}")
    return n_novel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdicts", action="store_true",
                    help="apply the by-hand verdicts in codebook/novelty_verdicts.yaml")
    ap.add_argument("--threshold", type=float, default=None,
                    help="override the control-calibrated line (not recommended)")
    a = ap.parse_args()

    con = dbm.connect()
    if a.verdicts:
        return 0 if apply_verdicts(con) else 1
    priors = yaml.safe_load((ROOT / "codebook" / "priors_v1.yaml").read_text())["priors"]
    rows = [dict(r) for r in con.execute(
        "SELECT insight_id, statement, so_what, kind FROM insights ORDER BY insight_id")]
    if not rows:
        print("no insights — run insights.py first")
        return 1

    from openai import OpenAI
    client = OpenAI(api_key=envm.load()["OPENAI_API_KEY"], timeout=120.0)

    with rmod.Run(con, "novelty", model=EMBED_MODEL, n_priors=len(priors),
                  threshold=a.threshold) as run:
        run.n_input = len(rows)
        P = embed(client, [p["statement"] for p in priors], run)
        I = embed(client, [r["statement"] for r in rows], run)
        sims = I @ P.T

        ctrl = controls(con)
        C = embed(client, ctrl, run)
        ctrl_max = np.sort((C @ P.T).max(axis=1))
        threshold = (a.threshold if a.threshold is not None
                     else float(np.quantile(ctrl_max, CONTROL_QUANTILE)))
        print(f"control set: {len(ctrl)} deliberate restatements, non-novel by "
              f"construction")
        print(f"  their similarity to the nearest prior: min {ctrl_max[0]:.3f}  "
              f"median {np.median(ctrl_max):.3f}  max {ctrl_max[-1]:.3f}")
        print(f"  calibrated line = {CONTROL_QUANTILE:.0%} quantile = {threshold:.3f}"
              + ("  (OVERRIDDEN)" if a.threshold is not None else "") + "\n")
        a.threshold = threshold

        print(f"{len(rows)} insights vs {len(priors)} pre-registered priors\n")
        flagged = 0
        for i, r in enumerate(rows):
            j = int(np.argmax(sims[i]))
            best, pid = float(sims[i][j]), priors[j]["id"]
            novel = int(best < a.threshold)
            flagged += novel
            con.execute(
                "UPDATE insights SET novelty = ?, nearest_prior = ?, nearest_similarity = ?"
                " WHERE insight_id = ?", (novel, pid, best, r["insight_id"]))
            mark = "  <-- NOVELTY CANDIDATE" if novel else ""
            print(f"{r['insight_id']} [{r['kind']:<13}] max sim {best:.3f} "
                  f"nearest {pid} ({','.join(priors[j]['codes'])}){mark}")
            print(f"    insight: {r['statement'][:150]}")
            print(f"    prior  : {priors[j]['statement'][:150]}\n")
        con.commit()
        run.n_output = flagged

        print(f"\n{flagged} of {len(rows)} flagged as novelty candidates.")
        print("This is a SHORTLIST. Read each candidate against its nearest prior and "
              "record the verdict by hand in the gate report — the score does not decide "
              "AC-6 (evals.md S3-MET-1).")
        if not flagged:
            print("\nNothing cleared the filter. Before reporting AC-6 as unmet, inspect "
                  "`analysis_cluster_code` and the blind Track B labels: a theme the "
                  "codebook cuts through will not look novel sentence-by-sentence "
                  "(EC-INS-7).")
        print(f"\ncost ${run.cost_usd() or 0:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
