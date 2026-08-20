"""The citation contract — what an insight is allowed to cite, and the check
that it actually resolves.

EC-INS-6 is the last hallucination surface in the pipeline. Everything upstream
is anchored: a classification carries an evidence span verified as an exact
substring, a crosstab is arithmetic over those classifications. Synthesis is
the one step where a model writes prose, and prose can assert a number that
exists nowhere.

The defence is structural rather than instructional. Insight generation reads
ONLY the materialised `analysis_*` tables, and every insight must name the row
it came from as `{table, key}`. `resolve()` then goes and looks. An insight
whose citation does not resolve is rejected — not softened, not flagged for
review. That turns "the model was told to cite its sources" into "the claim
was checked against the database", which are different guarantees.

`key` is the primary key with its parts joined by `|`, in the order given in
CITABLE. One shape for every table means the model has one rule to follow and
the checker has one path to test.
"""

from __future__ import annotations

import sqlite3

# table -> key columns, in the order they appear in a `key` string.
CITABLE: dict[str, tuple[str, ...]] = {
    "analysis_code_prevalence":       ("code",),
    "analysis_opportunity":           ("code",),
    "analysis_evidence_strength":     ("code",),
    "analysis_workaround":            ("code",),
    "analysis_counterfactuals":       ("code",),
    "analysis_weight_sensitivity":    ("code",),
    "analysis_stage_outcome":         ("stage", "outcome"),
    "analysis_stage_inversion":       ("stage",),
    "analysis_cooccurrence":          ("code_a", "code_b"),
    "analysis_segment_code_v2":       ("segment_id", "code"),
    "analysis_segment_recommendation": ("segment_id",),
    "analysis_source_code":           ("source", "code"),
    "analysis_cluster_code":          ("space", "cluster_id", "code"),
    "analysis_addressable":           ("bucket",),
    "analysis_subcode":               ("theme", "subcode"),
    "cluster_labels":                 ("space", "cluster_id"),
}


class CitationError(ValueError):
    pass


def resolve(con: sqlite3.Connection, table: str, key: str) -> dict:
    """Return the cited row, or raise. The caller rejects the insight."""
    cols = CITABLE.get(table)
    if cols is None:
        raise CitationError(
            f"`{table}` is not a citable analysis table — insights may cite only "
            f"{', '.join(sorted(CITABLE))}")
    parts = [p.strip() for p in str(key).split("|")]
    if len(parts) != len(cols):
        raise CitationError(
            f"{table} takes a {len(cols)}-part key ({'|'.join(cols)}), got {key!r}")
    where = " AND ".join(f"{c} = ?" for c in cols)
    row = con.execute(f"SELECT * FROM {table} WHERE {where}", parts).fetchone()
    if row is None:
        raise CitationError(f"{table}[{key}] does not exist")
    return dict(row)


def check(con: sqlite3.Connection, cites: list[dict]) -> tuple[list[dict], list[str]]:
    """(resolved rows, human-readable failures). An empty cite list is itself a
    failure — an uncited insight is exactly the thing EC-INS-6 forbids."""
    if not cites:
        return [], ["no citation given"]
    rows, bad = [], []
    for c in cites:
        try:
            rows.append(resolve(con, str(c.get("table", "")), str(c.get("key", ""))))
        except CitationError as e:
            bad.append(str(e))
    return rows, bad
