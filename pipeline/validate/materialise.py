"""Materialise Channel 4's evidence -- gold agreement per code, and the
registered method flags.

WHY THIS EXISTS
---------------
`score.py` computes per-code agreement and prints it to a terminal. That was
right for a gate taken by a human reading output once. It is wrong for P4,
where the chatbot must state classifier reliability IN AN ANSWER, and where
S4-INV-2 checks every numeral in that answer against a retrieved row. A number
that lives only in stdout cannot be cited and cannot be verified, so a model
asked for it will supply one from somewhere else.

So the same arithmetic is run again here and written to `analysis_gold_agreement`.
No new judgement, no LLM call, no re-labelling -- `score.py` remains the human
-readable report and this is the machine-readable one, both computed from the
same `gold` rows by the same functions.

THE VERDICT COLUMN IS THE POINT
-------------------------------
A kappa on its own invites the reader to compare it against 0.60 and move on.
What an answer actually needs is the sentence that must accompany a claim
resting on that code -- "the human coder and the classifier disagreed about
what this code MEANS" is a different warning from "too few gold labels to
tell", and the second is not a weaker version of the first. `verdict` and
`caveat` carry that distinction into the retrieval layer so the answer does not
have to re-derive it.

Usage:
    python pipeline/validate/materialise.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm          # noqa: E402
from pipeline.common import runs as rmod       # noqa: E402
from pipeline.validate import score as sc      # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FLAGS_PATH = ROOT / "codebook" / "method_flags.yaml"

# Matches score.py. A code the labeller applied fewer than five times has no
# interpretable kappa; see that module's note on why 0.00 would be a lie.
MIN_SUPPORT = 5
KAPPA_THRESHOLD = 0.60      # T-4


def _verdict(gold_n: int, kappa: float | None) -> tuple[str, str]:
    """(verdict, caveat). The caveat is written to be quoted verbatim into an
    answer's Confidence or Limitations section."""
    if gold_n < MIN_SUPPORT or kappa is None:
        return ("not measurable",
                f"Only {gold_n} gold label(s) carry this code, below the {MIN_SUPPORT} "
                "needed for an interpretable agreement statistic. Its reliability is "
                "unknown -- which is not the same as poor.")
    if kappa >= KAPPA_THRESHOLD:
        return ("reliable",
                f"Agreement with the human coder clears the 0.60 threshold "
                f"(kappa {kappa:.2f}).")
    if kappa >= 0.40:
        return ("weak",
                f"Agreement with the human coder is below the 0.60 threshold "
                f"(kappa {kappa:.2f}). The boundary is contested; treat an "
                "ordering that depends on this code as provisional.")
    return ("unreliable",
            f"Agreement with the human coder is poor (kappa {kappa:.2f}). The "
            "human and the classifier were substantially not applying the same "
            "definition. Any claim resting on this code must say so.")


def gold_agreement(con, run_id: str) -> int:
    rows = sc.load(con)
    both = [d for d in rows if d["gold_rel"] == 1 and d["model_rel"] == 1]
    if not both:
        print("no gold pool -- nothing to materialise")
        return 0

    codes = sorted({c for d in both for c in (d["gold_codes"] | d["model_codes"])})
    con.execute("DELETE FROM analysis_gold_agreement WHERE run_id = ?", (run_id,))
    n = 0
    for c in codes:
        a = [1 if c in d["gold_codes"] else 0 for d in both]
        b = [1 if c in d["model_codes"] else 0 for d in both]
        agree = sum(x == y for x, y in zip(a, b)) / len(both)
        kp = sc.kappa(a, b)
        gold_n, model_n = sum(a), sum(b)
        both_n = sum(x and y for x, y in zip(a, b))
        measurable = int(gold_n >= MIN_SUPPORT and kp is not None)
        verdict, caveat = _verdict(gold_n, kp if measurable else None)
        con.execute(
            "INSERT INTO analysis_gold_agreement (code, gold_n, model_n, both_n,"
            " agreement, kappa, measurable, verdict, caveat, gold_pool_n, run_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (c, gold_n, model_n, both_n, round(agree, 4),
             None if kp is None else round(kp, 4), measurable, verdict, caveat,
             len(both), run_id))
        n += 1
    con.commit()
    print(f"analysis_gold_agreement: {n} codes over a gold pool of {len(both)}")
    return n


def method_flags(con, run_id: str) -> int:
    doc = yaml.safe_load(FLAGS_PATH.read_text())
    con.execute("DELETE FROM analysis_method_flags WHERE run_id = ?", (run_id,))
    for f in doc["flags"]:
        con.execute(
            "INSERT INTO analysis_method_flags (flag_id, scope, applies_to,"
            " severity, statement, basis, run_id) VALUES (?,?,?,?,?,?,?)",
            (f["flag_id"], f["scope"], json.dumps(f["applies_to"]), f["severity"],
             " ".join(str(f["statement"]).split()), f.get("basis"), run_id))
    con.commit()
    print(f"analysis_method_flags: {len(doc['flags'])} flags")
    return len(doc["flags"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", help="reuse an existing run_id instead of opening one")
    a = ap.parse_args()

    con = dbm.init()          # idempotent -- applies the two new CREATE TABLEs
    if a.run_id:
        gold_agreement(con, a.run_id)
        method_flags(con, a.run_id)
        print(f"run_id {a.run_id}")
        return 0
    with rmod.Run(con, "method-materialise", model=None,
                  prompt_version=None) as run:
        run.n_output = gold_agreement(con, run.run_id) + method_flags(con, run.run_id)
        print(f"run_id {run.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
