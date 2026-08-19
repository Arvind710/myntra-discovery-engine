"""Codebook loading, validation, and the FREEZE mechanism (FR-5.6).

The codebook is the bedrock of the analysis: every number the engine
reports is computed against it. It is frozen before scoring, and a version
bump forces full re-classification (NFR-3, AR-3).

`load()` refuses to return a codebook whose content hash differs from the
recorded frozen hash. That turns FR-5.6 from a stated policy into an
enforced one -- an edit mid-run raises rather than silently splitting the
corpus across two codebook versions (EC-CLS-16).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CODEBOOK_DIR = ROOT / "codebook"
FREEZE_FILE = CODEBOOK_DIR / "FROZEN.json"

PHASES = {"eliminator", "confidence", "trigger", "na"}
OUTCOMES = {"exit", "defer", "na"}
STAGES = {"A", "B", "C", "D", "Z"}
SOLVABLE = {True, False, "partly", "na"}
TRANSFERABILITY = {"high", "medium", "low"}

EXPECTED_N_CODES = 33          # excludes Z-99 (AC-10, T-8)
EXPECTED_PER_STAGE = {"A": 7, "B": 8, "C": 14, "D": 4}


class CodebookError(RuntimeError):
    """Raised on any structural violation, or on a broken freeze."""


@dataclass(frozen=True)
class Codebook:
    version: str
    content_hash: str
    codes: dict[str, dict[str, Any]]      # id -> code dict, insertion-ordered
    contradictions: dict[str, Any]
    meta: dict[str, Any]
    segments: dict[str, Any]

    @property
    def version_string(self) -> str:
        """What gets stamped on every row: v1:ab12cd34 (EC-CLS-16)."""
        return f"{self.version}:{self.content_hash[:8]}"

    @property
    def scored_codes(self) -> list[str]:
        """The 33. Z-99 is the residual bucket, not one of them."""
        return [c for c, d in self.codes.items() if not d.get("is_residual")]

    def by_stage(self, stage: str) -> list[dict[str, Any]]:
        """Pass-2 sees only the codes in the assigned stage (<=14, not 33)."""
        out = [d for d in self.codes.values() if d["stage"] == stage]
        return sorted(out, key=lambda d: d["journey_rank"])

    def phase_of(self, code: str) -> str:
        return self.codes[code]["phase"]

    def allows_outcome(self, code: str, outcome: str) -> bool:
        return outcome in self.codes[code]["outcome_allowed"]

    def contradicts(self, codes: list[str]) -> list[tuple[str, str]]:
        """Return violating (code_a, code_b) pairs. EC-CLS-4 / S2-INV-3."""
        bad: list[tuple[str, str]] = []
        groups = self.contradictions.get("mutually_exclusive_groups", [])
        present = [c for c in codes if c in self.codes]
        for g in groups:
            anchors = [c for c in g.get("codes", []) if c in present]
            if not anchors:
                continue
            if g.get("pairwise"):
                for a in anchors:
                    for b in g["codes"]:
                        if b != a and b in present:
                            bad.append(tuple(sorted((a, b))))  # type: ignore[arg-type]
            for phase in g.get("excludes_phase", []):
                for other in present:
                    if other in anchors:
                        continue
                    if self.phase_of(other) == phase:
                        bad.append(tuple(sorted((anchors[0], other))))  # type: ignore[arg-type]
        return sorted(set(bad))


def _content_hash(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _validate(codes: dict[str, dict[str, Any]], contradictions: dict[str, Any]) -> None:
    scored = [c for c, d in codes.items() if not d.get("is_residual")]

    if len(scored) != EXPECTED_N_CODES:
        raise CodebookError(
            f"expected {EXPECTED_N_CODES} scored codes, found {len(scored)}: {scored}"
        )

    per_stage: dict[str, list[str]] = {}
    for cid in scored:
        per_stage.setdefault(codes[cid]["stage"], []).append(cid)
    for stage, want in EXPECTED_PER_STAGE.items():
        got = per_stage.get(stage, [])
        if len(got) != want:
            raise CodebookError(f"stage {stage}: expected {want} codes, found {len(got)}: {got}")

    required = (
        "stage", "name", "phase", "outcome_default", "outcome_allowed",
        "journey_rank", "solvable_without_money", "boundary_note",
        "transferability",
    )
    for cid, d in codes.items():
        for field in required:
            if field not in d or d[field] is None or d[field] == "":
                raise CodebookError(f"{cid}: missing or empty required field `{field}` (P0-2)")
        if d["stage"] not in STAGES:
            raise CodebookError(f"{cid}: bad stage {d['stage']!r}")
        if d["phase"] not in PHASES:
            raise CodebookError(f"{cid}: bad phase {d['phase']!r}")
        if d["outcome_default"] not in OUTCOMES:
            raise CodebookError(f"{cid}: bad outcome_default {d['outcome_default']!r}")
        for o in d["outcome_allowed"]:
            if o not in OUTCOMES:
                raise CodebookError(f"{cid}: bad outcome_allowed member {o!r}")
        if d["outcome_default"] not in d["outcome_allowed"]:
            raise CodebookError(f"{cid}: outcome_default not in outcome_allowed")
        if d["solvable_without_money"] not in SOLVABLE:
            raise CodebookError(
                f"{cid}: solvable_without_money must be yes/no/partly/na, "
                f"got {d['solvable_without_money']!r}"
            )
        if d["transferability"] not in TRANSFERABILITY:
            raise CodebookError(
                f"{cid}: transferability must be high/medium/low, got {d['transferability']!r}")
        if len(str(d["boundary_note"]).strip()) < 40:
            raise CodebookError(f"{cid}: boundary_note too thin to do its job (P0-2)")

    # P0-3: journey_rank is a TOTAL ORDER with no ties WITHIN a stage.
    # Blocking-code determination is a min() over this (arch §7.1); a tie
    # would make the blocking code non-deterministic and break NFR-3.
    for stage, cids in per_stage.items():
        ranks = [codes[c]["journey_rank"] for c in cids]
        if len(set(ranks)) != len(ranks):
            dupes = {r for r in ranks if ranks.count(r) > 1}
            raise CodebookError(f"stage {stage}: journey_rank ties at {sorted(dupes)} (P0-3)")

    # P0-4: contradiction block present, and every code it names exists.
    groups = contradictions.get("mutually_exclusive_groups")
    if not groups:
        raise CodebookError("contradiction matrix missing (P0-4 / EC-CLS-4)")
    for g in groups:
        for cid in g.get("codes", []):
            if cid not in codes:
                raise CodebookError(f"contradiction names unknown code {cid!r}")
        for phase in g.get("excludes_phase", []):
            if phase not in PHASES:
                raise CodebookError(f"contradiction names unknown phase {phase!r}")


def load(*, enforce_freeze: bool = True) -> Codebook:
    cb_path = CODEBOOK_DIR / "codebook_v1.yaml"
    seg_path = CODEBOOK_DIR / "segments_v1.yaml"

    raw = yaml.safe_load(cb_path.read_text())
    seg = yaml.safe_load(seg_path.read_text())

    codes = {c["id"]: c for c in raw["codes"]}
    if len(codes) != len(raw["codes"]):
        raise CodebookError("duplicate code id in codebook_v1.yaml")

    contradictions = raw.get("contradictions", {})
    _validate(codes, contradictions)

    digest = _content_hash(cb_path, seg_path)

    if enforce_freeze and FREEZE_FILE.exists():
        frozen = json.loads(FREEZE_FILE.read_text())
        if frozen["content_hash"] != digest:
            raise CodebookError(
                "CODEBOOK MUTATED AFTER FREEZE.\n"
                f"  frozen: {frozen['content_hash'][:16]}  ({frozen['frozen_at']})\n"
                f"  now:    {digest[:16]}\n"
                "FR-5.6: a codebook change requires an explicit version bump and a\n"
                "FULL re-classification. Half the corpus scored against v1 and half\n"
                "against v2 is a hard error (EC-CLS-16), not a warning.\n"
                "To bump: create codebook_v2.yaml, then re-freeze."
            )

    meta = {k: v for k, v in raw.items() if k not in ("codes", "contradictions")}
    return Codebook(
        version=raw["version"],
        content_hash=digest,
        codes=codes,
        contradictions=contradictions,
        meta=meta,
        segments=seg,
    )


def freeze(note: str = "") -> dict[str, Any]:
    """Record the content hash. Called once, at the P0 gate."""
    from datetime import datetime, timezone

    cb = load(enforce_freeze=False)
    payload = {
        "version": cb.version,
        "content_hash": cb.content_hash,
        "version_string": cb.version_string,
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_scored_codes": len(cb.scored_codes),
        "note": note,
    }
    FREEZE_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "freeze":
        print(json.dumps(freeze(" ".join(sys.argv[2:])), indent=2))
    else:
        cb = load()
        print(f"{cb.version_string}  |  {len(cb.scored_codes)} scored codes + Z-99")
        for stage in ("A", "B", "C", "D"):
            ids = [d["id"] for d in cb.by_stage(stage)]
            print(f"  {stage} ({len(ids):>2}): {' '.join(ids)}")
