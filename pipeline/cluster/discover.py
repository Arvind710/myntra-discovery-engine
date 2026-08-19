"""Track B — bottom-up clustering. The only check on codebook blindness.

WHAT THIS IS FOR
----------------
Track A asks "how much of the corpus does each pre-registered code explain?"
That question cannot discover a barrier nobody hypothesised: a theme outside
the 33 codes lands in Z-99 and is invisible as a *theme*. Track B asks the
opposite question — "what groups together if we ignore the codebook entirely?"
— and the disagreement between the two is the finding.

Three things depend on it:
  * **AC-11 / FR-5.4.** Z-99 is 31.7% against a 15% ceiling. Clustering the
    residual SEPARATELY (`space='z99'`, plan 2.11) is the mechanism for asking
    whether a real code is hiding in there.
  * **AC-6 novelty.** If the corpus only confirms the 28 pre-registered
    hypotheses, that must be reported honestly — but novelty, where it exists,
    usually surfaces here first.
  * **Codebook blindness (R-9).** Appendix C calls Track B the only protection
    against it, and says to cut it last and only with the consequence written
    into the deck.

WHY UMAP AND NOT PCA
--------------------
HDBSCAN is density-based, and density is close to meaningless at 1536
dimensions — distances concentrate, so everything looks equidistant and
nearly every point becomes noise. The reduction step is not a convenience,
it is what makes the clustering well-posed.

PCA was available without a dependency fight and was rejected. It is a linear
projection, and the neighbourhood structure of text embeddings is not linear;
projecting to 10 components would discard exactly the local structure HDBSCAN
needs. The visible consequence would have been a high noise fraction — which
S2-CLU-1 would then have reported as "Track B is weak", a statement about the
DATA, when it was really an artefact of my dependency workaround. A method
substitution that produces a plausible-looking wrong conclusion is the failure
mode this project is built to avoid, so the dependency was fixed instead.

DETERMINISM (EC-CLU-3 / S2-CLU-2, T-12 = 100%)
----------------------------------------------
UMAP is stochastic unless seeded. `random_state` is set, which also forces
single-threaded execution — slower, and correct. A clustering that changes
between runs cannot support a claim in a deck.

BLINDING (EC-CLU-4 / S2-CLU-4)
------------------------------
The labelling prompt contains verbatim record excerpts and NOTHING ELSE. No
code names, no code definitions, no stage names, no hypothesis list. If the
labeller sees the codebook it will describe clusters in the codebook's
vocabulary, every cluster will map neatly onto an existing code, and Track B
will confirm Track A by construction — producing exactly the reassuring
agreement it exists to falsify. `assert_prompt_is_blind()` enforces this at
run time rather than trusting the prompt text to stay clean.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.cluster import embed as emb  # noqa: E402
from pipeline.common import codebook as cbm  # noqa: E402
from pipeline.common import db as dbm  # noqa: E402
from pipeline.common import env as envm  # noqa: E402
from pipeline.common import runs as rmod  # noqa: E402

SEED = 20260820
UMAP_KW = dict(n_neighbors=15, min_dist=0.0, n_components=10, metric="cosine")
N_EXEMPLARS = 8
EXCERPT_CHARS = 420

LABEL_SYSTEM = (
    "You are grouping anonymous excerpts of public feedback from online fashion "
    "shoppers. Each group was formed by statistical similarity alone; you are "
    "seeing it for the first time.\n\n"
    "Name what the people in THIS group have in common, using their own framing. "
    "Do not force a group into a tidy category, do not invent a cause the text "
    "does not state, and if the group looks incoherent say so plainly — "
    '"mixed / no common theme" is a valid and useful answer.\n\n'
    "Return JSON: {\"label\": \"<= 6 words\", \"description\": \"1-2 sentences\", "
    "\"coherent\": true|false}"
)


def assert_prompt_is_blind(prompt: str) -> None:
    """S2-CLU-4, enforced rather than asserted in prose.

    A single code id leaking into the prompt is enough to steer every label,
    and the result would look like independent corroboration of the codebook.
    """
    cb = cbm.load()
    lowered = prompt.lower()
    leaked = [c for c in cb.codes if c.lower() in lowered.split()]
    for c, d in cb.codes.items():
        if d.get("name") and d["name"].lower() in lowered:
            leaked.append(c)
    if leaked:
        raise RuntimeError(
            f"cluster-labelling prompt leaks codebook content {sorted(set(leaked))} — "
            "Track B would confirm Track A by construction (EC-CLU-4)")


def populations(con) -> dict[str, set[str]]:
    """`all` = every relevant record. `z99` = the residual, clustered on its own
    so a real code hiding in 31.7% of the corpus can surface (plan 2.11)."""
    z99 = {r[0] for r in con.execute(
        "SELECT DISTINCT record_id FROM classifications WHERE code LIKE 'Z%'")}
    rel = {r[0] for r in con.execute(
        "SELECT record_id FROM relevance WHERE is_relevant=1")}
    return {"all": rel, "z99": z99 & rel}


def reduce_and_cluster(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    import umap
    from sklearn.cluster import HDBSCAN

    n = X.shape[0]
    reducer = umap.UMAP(random_state=SEED, **UMAP_KW)
    Y = reducer.fit_transform(X)
    # arch/plan 2.10: min_cluster_size = max(15, n/200). At n=1,199 the floor
    # binds; the n/200 term matters only if the corpus grows.
    mcs = max(15, n // 200)
    labels_ = HDBSCAN(min_cluster_size=mcs, min_samples=None,
                      cluster_selection_method="eom").fit(Y)
    return labels_.labels_, getattr(labels_, "probabilities_", np.ones(n))


def exemplars(ids: list[str], labels: np.ndarray, probs: np.ndarray,
              cid: int) -> list[str]:
    """Highest-probability members: the points HDBSCAN is most confident sit in
    the dense core, so they describe the cluster rather than its fringe."""
    idx = np.where(labels == cid)[0]
    order = idx[np.argsort(-probs[idx])]
    return [ids[i] for i in order[:N_EXEMPLARS]]


def label_clusters(con, space: str, ids: list[str], labels: np.ndarray,
                   probs: np.ndarray, run_id: str, model: str) -> None:
    from openai import OpenAI
    client = OpenAI(api_key=envm.load()["OPENAI_API_KEY"], timeout=180.0)

    text_of = {r["record_id"]: r["text_clean"] for r in con.execute(
        "SELECT record_id, text_clean FROM records")}

    for cid in sorted({int(c) for c in labels if c >= 0}):
        ex = exemplars(ids, labels, probs, cid)
        excerpts = "\n\n".join(
            f"[{i + 1}] {text_of.get(r, '')[:EXCERPT_CHARS]}" for i, r in enumerate(ex))
        prompt = f"Group of {int((labels == cid).sum())} excerpts:\n\n{excerpts}"
        assert_prompt_is_blind(prompt)

        resp = client.chat.completions.create(
            model=model, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": LABEL_SYSTEM},
                      {"role": "user", "content": prompt}])
        out = json.loads(resp.choices[0].message.content)
        con.execute(
            "INSERT OR REPLACE INTO cluster_labels (cluster_id, space, label,"
            " description, size, exemplar_ids, run_id) VALUES (?,?,?,?,?,?,?)",
            (cid, space, str(out.get("label", ""))[:120],
             str(out.get("description", "")), int((labels == cid).sum()),
             json.dumps(ex), run_id))
        flag = "" if out.get("coherent", True) else "   [labeller: not coherent]"
        print(f"    c{cid:<3} n={int((labels == cid).sum()):<4} {out.get('label','')}{flag}")
    con.commit()


def run_space(con, space: str, model: str, do_label: bool) -> dict:
    ids_all, X_all = emb.load()
    keep = populations(con)[space]
    sel = [i for i, r in enumerate(ids_all) if r in keep]
    if len(sel) < 30:
        print(f"  {space}: only {len(sel)} records — skipped")
        return {}
    ids = [ids_all[i] for i in sel]
    X = X_all[sel]
    print(f"\n=== space '{space}' — {len(ids)} records ===")

    labels, probs = reduce_and_cluster(X)
    n_clusters = len({int(c) for c in labels if c >= 0})
    noise = float((labels < 0).mean())
    sizes = [int((labels == c).sum()) for c in {int(c) for c in labels if c >= 0}]
    biggest = max(sizes) / len(ids) if sizes else 0.0

    with rmod.Run(con, f"cluster-{space}", model=model, seed=SEED,
                  umap=json.dumps(UMAP_KW), n=len(ids)) as run:
        run.n_input = len(ids)
        con.execute("DELETE FROM clusters WHERE space=?", (space,))
        con.executemany(
            "INSERT INTO clusters (record_id, cluster_id, probability, space, run_id)"
            " VALUES (?,?,?,?,?)",
            [(r, int(c), float(p), space, run.run_id)
             for r, c, p in zip(ids, labels, probs)])
        con.execute("DELETE FROM cluster_labels WHERE space=?", (space,))
        con.commit()
        run.n_output = n_clusters
        if do_label:
            label_clusters(con, space, ids, labels, probs, run.run_id, model)

    print(f"  clusters {n_clusters} · noise {noise:.1%} · largest {biggest:.1%}")
    print(f"  S2-CLU-1 noise < 60%      : {'PASS' if noise < 0.60 else 'FAIL — declare Track B weak'}")
    print(f"  S2-CLU-3 largest < 50%    : {'PASS' if biggest < 0.50 else 'FAIL — re-tune'}")
    return {"space": space, "n": len(ids), "clusters": n_clusters,
            "noise": noise, "largest": biggest}


def main() -> int:
    ap = argparse.ArgumentParser(description="Track B clustering")
    ap.add_argument("--space", choices=["all", "z99", "both"], default="both")
    ap.add_argument("--no-label", action="store_true", help="cluster only, no LLM calls")
    ap.add_argument("--model", default=rmod.CLASSIFIER_MODEL)
    ap.add_argument("--determinism", action="store_true",
                    help="S2-CLU-2 / T-12: cluster twice and compare assignments")
    a = ap.parse_args()

    con = dbm.connect()
    spaces = ["all", "z99"] if a.space == "both" else [a.space]

    if a.determinism:
        ids_all, X_all = emb.load()
        keep = populations(con)["all"]
        sel = [i for i, r in enumerate(ids_all) if r in keep]
        l1, _ = reduce_and_cluster(X_all[sel])
        l2, _ = reduce_and_cluster(X_all[sel])
        same = float((l1 == l2).mean())
        print(f"S2-CLU-2 / T-12 determinism: {same:.1%} "
              f"{'PASS' if same == 1.0 else 'FAIL'}")
        return 0 if same == 1.0 else 1

    for s in spaces:
        run_space(con, s, a.model, not a.no_label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
