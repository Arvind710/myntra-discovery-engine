"""The evidence packet — the ONLY thing insight generation is allowed to read.

FR-3.1 and EC-INS-6 turn on one structural rule: synthesis reads the
materialised `analysis_*` tables, never raw records. That rule is enforced
here, by construction, rather than by asking the model nicely. If a fact is not
in this packet it cannot enter an insight, and every row in the packet is
addressable by the `{table, key}` contract in `citations.py`, so anything the
model says can be traced back to a row that exists.

The packet is rendered as compact pipe-delimited tables rather than JSON: it is
roughly a third of the tokens for the same content, and the leading `key=`
column makes the citation the model must write visible beside the numbers it
is reading, which is where it belongs.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import codebook as cbm  # noqa: E402

MIN_N_VISIBLE = 15


def _table(title: str, note: str, key_cols: tuple[str, ...],
           rows: list[sqlite3.Row], cols: list[str], fmt: dict | None = None) -> str:
    fmt = fmt or {}
    # The key is wrapped in backticks and separated by "::" because a plain
    # "key | col1 | col2" header led the model to cite "4 | Stuck Deciders" —
    # it read the first data column as part of the key. Loosening the checker
    # to accept that would have discarded the contract to fix a display bug.
    out = [f"### {title}", f"_{note}_" if note else "",
           "cite key :: " + " | ".join(cols)]
    for r in rows:
        d = dict(r)
        key = "|".join(str(d[c]) for c in key_cols)
        vals = []
        for c in cols:
            v = d.get(c)
            if v is None:
                vals.append("–")
            elif c in fmt:
                vals.append(fmt[c](v))
            elif isinstance(v, float):
                vals.append(f"{v:.3f}")
            else:
                vals.append(str(v))
        out.append(f"`{key}` :: " + " | ".join(vals))
    return "\n".join(x for x in out if x) + "\n"


def build(con: sqlite3.Connection) -> str:
    cb = cbm.load()
    q = lambda sql, p=(): list(con.execute(sql, p))  # noqa: E731
    parts: list[str] = []

    parts.append(
        "# EVIDENCE PACKET\n"
        "Every table below is a materialised analysis table. Each row begins with its\n"
        "citation key in `backticks`, followed by `::` and then the row's values. Cite\n"
        "EXACTLY the backticked text — nothing after the `::` is part of the key.\n"
        "Shares are shares of DISCUSSION — how often something is talked about — and "
        "are never drop-off, conversion or funnel rates. No user-level data exists.\n")

    # Method & limitations travel WITH the evidence, not in an appendix. A
    # hypothesis written without them will be written as if the classifier were
    # perfect, and the caveat then has to be retro-fitted by a human who may not
    # know which claims it applies to. P4 builds this as retrieval Channel 4
    # (arch §8.4) for the same reason; this is the same content, earlier.
    parts.append(
        "### METHOD & LIMITATIONS (context — not citable, but binding on what you may claim)\n"
        "- Corpus: 1,018 relevant records after excluding five low-yield subreddits. "
        "Sources: YouTube, Reddit (collected via a third-party service, disclosed), "
        "Google Play, App Store, plus verified published research.\n"
        "- Only ~36% of the corpus is Myntra-specific. Platform-mechanical codes "
        "(Stage B, D1–D3, C7, C8) are scored on their Myntra-specific n.\n"
        "- Agreement with a human coder was measured on 108 gold labels. Per-code kappa "
        "clears 0.60 for only 2 of the 5 codes with enough gold to measure: C1 0.66, "
        "C6 0.64; C3 0.52, C2 0.43, C10 0.10. 16 codes are too rare in gold to measure "
        "at all. THIS FAILS ITS THRESHOLD and is reported as failing.\n"
        "- C10 is UNRELIABLE (kappa 0.10): the human labeller read it as app permissions, "
        "the codebook means another person's approval. Any C10 claim must carry that caveat.\n"
        "- Relevance recall is an ESTIMATE of ~79% against an 85% threshold, not a "
        "measurement. It fails too.\n"
        "- Stage A is under-detected BY CONSTRUCTION: forgetting produces no complaint. "
        "A low Stage A count is not evidence that Stage A is small.\n"
        "- Segments are DERIVED from the classification, not observed. 'Not decided' is "
        "operationalised as the presence of a Confidence-phase code, so Confidence codes "
        "are barred from segments 1, 3 and 5 by definition and their lift into segment 4 "
        "is partly circular.\n"
        "- The corpus contains no user-level or funnel data of any kind.\n")

    parts.append("### codebook (for meaning only — not citable)\n" + "\n".join(
        f"{cid} | {d['name']} | stage {d['stage']} | {d['phase']} | "
        f"default outcome {d['outcome_default']} | solvable without money: "
        f"{d['solvable_without_money']}"
        for cid, d in cb.codes.items()) + "\n")

    parts.append(_table(
        "analysis_addressable", "AC-12 sizing: what was removed from the opportunity, and how big it was",
        ("bucket",), q("SELECT * FROM analysis_addressable"),
        ["label", "n", "share_of_corpus", "excluded"]))

    parts.append(_table(
        "analysis_code_prevalence", "n is records; n_distinct_authors is people. below_min_n=1 means never rank it",
        ("code",), q("SELECT * FROM analysis_code_prevalence ORDER BY n DESC"),
        ["stage", "n", "n_distinct_authors", "denominator", "share", "n_sources",
         "mean_confidence", "below_min_n"]))

    parts.append(_table(
        "analysis_opportunity", "six components each on 0-1, equal default weights; rank omitted below n=30",
        ("code",), q("SELECT * FROM analysis_opportunity ORDER BY score DESC"),
        ["stage", "n", "prevalence", "intensity", "defer_share", "solvable_without_money",
         "evidence_strength", "segment_fit", "score", "rank", "excluded"]))

    parts.append(_table(
        "analysis_weight_sensitivity", "share of 1,000 weightings (±30%) in which the code holds top rank",
        ("code",), q("SELECT * FROM analysis_weight_sensitivity ORDER BY top_share DESC"),
        ["top_share", "top3_share", "mean_rank", "p05_rank", "p95_rank"]))

    parts.append(_table(
        "analysis_stage_inversion", "how far a stage would have to be under-reported to overtake the leader",
        ("stage",), q("SELECT * FROM analysis_stage_inversion ORDER BY n DESC"),
        ["n", "share", "leader", "leader_n", "inversion_factor", "fragile"]))

    parts.append(_table(
        "analysis_stage_outcome", "defer = intent intact = the winnable population; exit = intent destroyed",
        ("stage", "outcome"), q("SELECT * FROM analysis_stage_outcome ORDER BY n DESC"),
        ["n", "denominator", "share"]))

    parts.append(_table(
        "analysis_subcode", "what the theme actually is. share is of the THEME, multi-label so it may sum above 1",
        ("theme", "subcode"), q("SELECT * FROM analysis_subcode ORDER BY theme, n DESC"),
        ["n", "n_theme", "share", "mean_confidence"]))

    parts.append(_table(
        "analysis_workaround", "effort spent is stronger evidence of unmet need than complaint volume",
        ("code",), q("SELECT * FROM analysis_workaround WHERE n_code >= ? ORDER BY intensity_index DESC",
                     (MIN_N_VISIBLE,)),
        ["n_with_workaround", "n_code", "share", "mean_effort", "intensity_index"]))

    parts.append(_table(
        "analysis_counterfactuals", "'I would have bought it if…' — the user naming their own unblock",
        ("code",), q("SELECT * FROM analysis_counterfactuals WHERE n_code >= ? ORDER BY share DESC",
                     (MIN_N_VISIBLE,)),
        ["n_counterfactual", "n_code", "share"]))

    parts.append(_table(
        "analysis_evidence_strength", "how well-supported the code is, independent of how big it is",
        ("code",), q("SELECT * FROM analysis_evidence_strength ORDER BY composite DESC"),
        ["n", "prevalence", "source_diversity", "counterfactual_rate", "workaround_rate",
         "mean_confidence", "composite"]))

    parts.append(_table(
        "analysis_cooccurrence", "lift >> 1 means two barriers are one compound problem, not two",
        ("code_a", "code_b"),
        q("SELECT * FROM analysis_cooccurrence WHERE min_support_met = 1 ORDER BY lift DESC LIMIT 25"),
        ["n_joint", "n_a", "n_b", "denominator", "lift", "pmi"]))

    parts.append(_table(
        "analysis_segment_code_v2", "segments are DERIVED structurally, not inferred from stated motivation",
        ("segment_id", "code"),
        q("SELECT * FROM analysis_segment_code_v2 WHERE n >= ? ORDER BY segment_id, n DESC",
          (MIN_N_VISIBLE,)),
        ["segment_name", "n", "n_distinct_authors", "denominator", "share", "below_min_n"]))

    parts.append(_table(
        "analysis_segment_recommendation", "basis records WHICH matrix carried it (EC-INS-8 fallback)",
        ("segment_id",), q("SELECT * FROM analysis_segment_recommendation ORDER BY score DESC"),
        ["segment_name", "n", "share", "basis", "rankable_cells", "solvable_n", "score",
         "recommended"]))

    parts.append(_table(
        "analysis_source_code", "js_divergence is per SOURCE: high means the code may be an artefact of who posts there",
        ("source", "code"),
        q("SELECT * FROM analysis_source_code WHERE n >= ? ORDER BY source, n DESC",
          (MIN_N_VISIBLE,)),
        ["n", "n_distinct_authors", "denominator", "share", "js_divergence"]))

    parts.append(_table(
        "cluster_labels",
        "TRACK B. Clusters were formed by statistical similarity and named BLIND — "
        "the labeller never saw the codebook. This is the only view of the corpus not "
        "shaped by the pre-registered categories",
        ("space", "cluster_id"), q("SELECT * FROM cluster_labels ORDER BY space, size DESC"),
        ["size", "label", "description"]))

    parts.append(_table(
        "analysis_cluster_code",
        "TRACK B x TRACK A. A cluster spread across many codes is a theme the codebook "
        "CUTS THROUGH; a cluster that is mostly Z-99 is a theme it MISSES. entropy is "
        "normalised 0-1: 0 = this cluster is one code, 1 = maximally spread",
        ("space", "cluster_id", "code"),
        q("SELECT * FROM analysis_cluster_code WHERE n >= 8 ORDER BY space, cluster_id, n DESC"),
        ["n", "cluster_size", "code_size", "entropy_code_to_cluster", "entropy_cluster_to_code"]))

    return "\n".join(parts)


if __name__ == "__main__":
    from pipeline.common import db as dbm
    text = build(dbm.connect(read_only=True))
    print(text)
    print(f"\n--- {len(text):,} chars ≈ {len(text)//4:,} tokens ---", file=sys.stderr)
