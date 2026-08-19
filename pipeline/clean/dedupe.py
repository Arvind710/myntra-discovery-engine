"""Deduplication — and the single most consequential rule in the build.

EC-CLEAN-1 is the failure this module exists to prevent, and it is silent:
fifty people independently posting "sizes run small" IS the finding. Any
near-duplicate pass that compares across authors reads that consensus as
duplication and deletes the strongest evidence in the corpus. The charts
look completely normal afterwards, and the deleted records leave no trace
in any denominator.

The rule, therefore:

    EXACT hash dedupe    -> across sources. Safe: the same text at the same
                            URL is genuinely one record (EC-CLEAN-2).
    NEAR dedupe (MinHash)-> ONLY within (source, author_hash). The same
                            person posting the same thing twice.
                            NEVER across authors. Not once, not with a
                            higher threshold, not "just to be safe".

Cross-author similarity is still COMPUTED — and stored in `consensus` as a
strength signal (P1-3). Measured and reported, never used to remove.

S1-PROBE-1 pins both directions: 40 distinct authors saying near-identical
things must all survive; 5 posts from one author must collapse to 1.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections import defaultdict
from typing import Any, Iterable

NEAR_DUPE_THRESHOLD = 0.85          # Jaccard, same-author only (long text)
NEAR_DUPE_THRESHOLD_SHORT = 0.60    # short text -- see near_dupe_threshold()
CONSENSUS_SIMILARITY = 0.35         # "these two people made the same claim"


def near_dupe_threshold(n_words: int) -> float:
    """A single substituted word costs proportionally more in short text.

    `architecture.md` §5.3 specifies Jaccard > 0.85, which is right for a
    paragraph. On a ten-word app-store review, "great product" vs "great
    products" scores 0.64 -- unmistakably the same person posting the same
    thing twice, and a fixed 0.85 lets it through. The threshold therefore
    scales with length, which compensates for the shingle-count effect
    rather than loosening the rule.

    This is only safe because EC-CLEAN-1 protection is STRUCTURAL: near-dupe
    never compares across authors, so a more sensitive threshold can never
    eat consensus. It can only merge one person's repeats more aggressively.
    """
    return NEAR_DUPE_THRESHOLD if n_words >= 25 else NEAR_DUPE_THRESHOLD_SHORT


def shingle_k(n_words: int) -> int:
    """Shingle width, scaled to text length.

    A fixed k=5 is wrong for short text: one substituted word breaks five
    consecutive shingles, so "great products" vs "great product" scores
    0.20 instead of ~0.95. App-store reviews are exactly this short, which
    is where review-farm variants live (EC-COL-8) -- a fixed-k pass would
    miss them entirely.

    Raising sensitivity is safe here in a way it would not be in a
    cross-author design: EC-CLEAN-1 protection is STRUCTURAL (we never
    compare across authors), not a function of the threshold. So the
    threshold can be tuned for recall without risking the consensus.
    """
    if n_words >= 25:
        return 5
    if n_words >= 12:
        return 3
    return 2

_NORM = re.compile(r"[^\w\s]+")
_WS = re.compile(r"\s+")


def normalise_for_hash(text: str) -> str:
    """Aggressive normalisation, used ONLY for comparison. `text_raw` is
    untouched -- EC-CLEAN-6, caps and '!!!!' carry the intensity signal."""
    t = _NORM.sub(" ", text.lower())
    return _WS.sub(" ", t).strip()


def exact_hash(text: str) -> str:
    return hashlib.sha1(normalise_for_hash(text).encode()).hexdigest()


def shingles(text: str, k: int | None = None) -> set[str]:
    words = normalise_for_hash(text).split()
    if k is None:
        k = shingle_k(len(words))
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def _pair_shingles(a: str, b: str) -> tuple[set[str], set[str]]:
    """Compare two texts at a shared width -- the SHORTER text's width, so a
    long/short pair is not compared at incompatible granularities."""
    wa, wb = normalise_for_hash(a).split(), normalise_for_hash(b).split()
    k = shingle_k(min(len(wa), len(wb)))
    return shingles(a, k), shingles(b, k)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def find_exact_duplicates(rows: list[dict]) -> list[tuple[str, str]]:
    """Return (loser_id, winner_id). Keeps the EARLIEST record (EC-CLEAN-2)."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[exact_hash(r["text_raw"])].append(r)

    out: list[tuple[str, str]] = []
    for group in buckets.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r.get("created_at") or "9999", r["record_id"]))
        winner = group[0]["record_id"]
        out.extend((r["record_id"], winner) for r in group[1:])
    return out


def find_author_near_duplicates(rows: list[dict]) -> list[tuple[str, str]]:
    """Near-duplicates WITHIN (source, author_hash) only.

    The scoping is not a performance optimisation -- it is the correctness
    property. Widening it to cross-author is the EC-CLEAN-1 bug.
    """
    by_author: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("author_hash"):        # anonymous rows are never near-deduped
            by_author[(r["source"], r["author_hash"])].append(r)

    out: list[tuple[str, str]] = []
    for group in by_author.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r.get("created_at") or "9999", r["record_id"]))
        kept: list[tuple[dict, int]] = []
        for r in group:
            nw_r = len(normalise_for_hash(r["text_raw"]).split())
            match = None
            for k, nw_k in kept:
                sa, sb = _pair_shingles(r["text_raw"], k["text_raw"])
                if jaccard(sa, sb) > near_dupe_threshold(min(nw_r, nw_k)):
                    match = k
                    break
            if match is not None:
                out.append((r["record_id"], match["record_id"]))
            else:
                kept.append((r, nw_r))
    return out


def _minhash(sh: set[str], num_perm: int = 64):
    from datasketch import MinHash
    m = MinHash(num_perm=num_perm)
    for x in sh:
        m.update(x.encode())
    return m


def measure_cross_author_consensus(rows: list[dict], *, threshold: float = CONSENSUS_SIMILARITY,
                                   num_perm: int = 64) -> list[dict]:
    """Cross-author similarity as a SIGNAL, not a filter (P1-3, EC-CLEAN-1).

    A record that many *different* people echo is strong evidence. This is
    the mirror image of the dedupe rule: the same measurement, used to
    weight a record up rather than to delete it.

    Implemented with MinHash LSH rather than the obvious pairwise loop.
    The naive version is O(n^2) *and* recomputes shingles inside the loop --
    at 5,150 records that is ~13M comparisons with two shingle builds each,
    which does not finish. LSH indexes once and only compares candidates.
    """
    from datasketch import MinHashLSH

    # k=2 for candidate generation: this stage optimises RECALL, and exact
    # Jaccard below makes the actual call. A wider shingle here silently
    # under-counts consensus on short text, which is the failure mode that
    # matters -- understated consensus reads as a weaker finding.
    prepared = [(r, shingles(r["text_raw"], k=2)) for r in rows if len(r["text_raw"]) > 30]
    if not prepared:
        return [{"record_id": r["record_id"], "max_jaccard_xauthor": 0.0,
                 "n_similar_xauthor": 0} for r in rows]

    # Slightly below the reporting threshold, so LSH over-generates
    # candidates and exact Jaccard makes the final call. Recall over
    # precision here: a missed echo understates consensus.
    lsh = MinHashLSH(threshold=max(threshold - 0.15, 0.15), num_perm=num_perm)
    sigs: dict[str, Any] = {}
    by_id: dict[str, tuple[dict, set[str]]] = {}

    for r, sh in prepared:
        m = _minhash(sh, num_perm)
        sigs[r["record_id"]] = m
        by_id[r["record_id"]] = (r, sh)
        lsh.insert(r["record_id"], m)

    scored: dict[str, dict] = {}
    for rid, (r, sh) in by_id.items():
        best, seen = 0.0, set()
        for cand in lsh.query(sigs[rid]):
            if cand == rid:
                continue
            other, osh = by_id[cand]
            oa = other.get("author_hash")
            if not oa or oa == r.get("author_hash"):
                continue
            sa, sb = _pair_shingles(r["text_raw"], other["text_raw"])
            j = jaccard(sa, sb)           # exact + adaptive, on candidates only
            if j > best:
                best = j
            if j > threshold:
                seen.add(oa)
        scored[rid] = {"record_id": rid, "max_jaccard_xauthor": round(best, 4),
                       "n_similar_xauthor": len(seen)}

    for r in rows:
        scored.setdefault(r["record_id"], {"record_id": r["record_id"],
                                           "max_jaccard_xauthor": 0.0,
                                           "n_similar_xauthor": 0})
    return [scored[r["record_id"]] for r in rows]


def run(con: sqlite3.Connection, run_id: str) -> dict[str, int]:
    rows = [dict(r) for r in con.execute(
        "SELECT record_id, source, author_hash, created_at, text_raw FROM records")]

    stats = {"input": len(rows), "exact": 0, "near": 0}

    for loser, winner in find_exact_duplicates(rows):
        con.execute(
            "INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason, detail, run_id)"
            " SELECT record_id, source, 'clean', 'dedupe/exact', ?, ? FROM records WHERE record_id=?",
            (f"duplicate of {winner}", run_id, loser))
        stats["exact"] += 1

    for loser, winner in find_author_near_duplicates(rows):
        con.execute(
            "INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason, detail, run_id)"
            " SELECT record_id, source, 'clean', 'dedupe/near', ?, ? FROM records WHERE record_id=?",
            (f"same-author near-duplicate of {winner}", run_id, loser))
        stats["near"] += 1

    for c in measure_cross_author_consensus(rows):
        con.execute(
            "INSERT OR REPLACE INTO consensus (record_id, max_jaccard_xauthor,"
            " n_similar_xauthor, run_id) VALUES (?,?,?,?)",
            (c["record_id"], c["max_jaccard_xauthor"], c["n_similar_xauthor"], run_id))

    con.commit()
    stats["retained"] = con.execute("SELECT count(*) FROM retained").fetchone()[0]
    return stats
