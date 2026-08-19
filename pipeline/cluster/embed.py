"""Embeddings for Track B clustering — stored WITH their record ids.

WHY THIS DOES NOT REUSE `data/embeddings.npy`
---------------------------------------------
The prefilter wrote an 8,639 x 1536 array whose only link to the corpus was
row position, produced by `SELECT record_id, source, text_clean FROM retained`
— an unordered SELECT over a VIEW. Nothing recorded which row was which
record.

That was already load-bearing and already wrong. Removing the stale prefilter
exclusion marks changed what `retained` returns (4,031 -> 8,647), so the array
and the view no longer describe the same population, and re-running the same
SELECT today would silently pair vectors with the wrong records. Clusters
built on that would be meaningless in a way no assertion downstream could
detect — every cluster would have a plausible size and an incoherent
membership.

So: ids and vectors are stored together in one .npz, the population is stated
explicitly rather than inherited from a view, and `load()` returns them as a
pair. Position is never the identifier.

WHAT IS EMBEDDED
----------------
The 1,199 relevant records — Track B exists to find themes the codebook
missed *within the material being coded*, so the irrelevant pool is not the
question. `text_clean` is used rather than `text_raw` because embeddings
should not be steered by markup and casing artefacts; the classifier reads
`text_raw` (EC-CLEAN-6) and that difference is deliberate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm  # noqa: E402
from pipeline.common import env as envm  # noqa: E402
from pipeline.common import runs as rmod  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "embeddings_relevant.npz"
BATCH = 256


def population(con) -> list[tuple[str, str]]:
    """(record_id, text) for every relevant record, ordered by id so the file
    is reproducible byte-for-byte across runs (NFR-3)."""
    return [(r["record_id"], r["text_clean"]) for r in con.execute(
        """SELECT r.record_id, r.text_clean
           FROM relevance v JOIN records r USING (record_id)
           WHERE v.is_relevant = 1
           ORDER BY r.record_id""")]


def build(con, *, model: str = rmod.EMBEDDING_MODEL) -> Path:
    rows = population(con)
    if not rows:
        raise SystemExit("no relevant records to embed")
    ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    print(f"embedding {len(ids)} relevant records with {model}")

    v = envm.load()
    from openai import OpenAI
    client = OpenAI(api_key=v["OPENAI_API_KEY"], timeout=180.0)

    vecs: list[list[float]] = []
    with rmod.Run(con, "embed-cluster", model=model, n=len(ids),
                  population="relevance.is_relevant=1") as run:
        run.n_input = len(ids)
        for i in range(0, len(texts), BATCH):
            chunk = texts[i:i + BATCH]
            resp = client.embeddings.create(model=model, input=chunk)
            # The API returns results in request order, but it also returns an
            # explicit index. Sorting on it costs nothing and removes the same
            # class of assumption this module exists to eliminate.
            vecs += [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
            run.add_usage(input_tokens=resp.usage.prompt_tokens)
            print(f"  {min(i + BATCH, len(texts))}/{len(texts)}")
        run.n_output = len(vecs)

    E = np.asarray(vecs, dtype=np.float32)
    assert E.shape[0] == len(ids), f"{E.shape[0]} vectors for {len(ids)} ids"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT, ids=np.array(ids, dtype=object), vecs=E)
    print(f"\nsaved {OUT.name}  {E.shape}  (LOCAL ONLY — gitignored, never deployed)")
    return OUT


def load() -> tuple[list[str], "np.ndarray"]:
    if not OUT.exists():
        raise SystemExit(f"{OUT.name} missing — run `python pipeline/cluster/embed.py`")
    z = np.load(OUT, allow_pickle=True)
    ids = [str(x) for x in z["ids"]]
    vecs = z["vecs"]
    assert len(ids) == vecs.shape[0], "id/vector length mismatch in the embedding file"
    return ids, vecs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Embed the relevant corpus for Track B")
    ap.add_argument("--force", action="store_true", help="re-embed even if the file exists")
    a = ap.parse_args()
    con = dbm.connect()
    if OUT.exists() and not a.force:
        ids, vecs = load()
        n_now = len(population(con))
        print(f"{OUT.name} already holds {len(ids)} vectors {vecs.shape}; "
              f"corpus has {n_now} relevant records.")
        if len(ids) != n_now:
            print("  ! counts differ — re-run with --force")
    else:
        build(con)
