"""Shared helpers for every collector.

Collectors are deliberately THIN: they fetch, map to the `records` schema,
and write. Deduplication, language detection, PII scrubbing and
normalisation are a separate stage (`pipeline/clean/`), so that what was
collected and what was kept remain separable — FR-1.6 needs both.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

# Salted author hash -- NFR-7. The handle NEVER enters the database.
# The salt lives in .env and is not committed, so the hashes cannot be
# reversed by anyone reading the repo.
_SALT = os.environ.get("AUTHOR_SALT", "")

DELETED_MARKERS = {"[deleted]", "[removed]", "", None}


def author_hash(handle: str | None) -> str | None:
    """Stable pseudonymous id. Same author -> same hash, across runs."""
    if not handle or handle in DELETED_MARKERS:
        return None
    if not _SALT:
        raise RuntimeError("AUTHOR_SALT is not set -- refusing to write unsalted hashes (NFR-7)")
    return hashlib.sha256(f"{_SALT}::{handle.strip().lower()}".encode()).hexdigest()[:32]


def record_id(source: str, native_id: str) -> str:
    """sha1(source || native_id). Re-ingest is idempotent by construction
    (EC-CLEAN-7) -- the same item collected twice writes the same row."""
    return hashlib.sha1(f"{source}‖{native_id}".encode()).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_iso(value: Any) -> str | None:
    """Sources disagree wildly on time format. NULL is valid (EC-COL-10):
    recency is computed only over records that have it, with coverage shown."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return None


_WS = re.compile(r"\s+")


def make_record(
    *,
    source: str,
    native_id: str,
    source_url: str,
    text_raw: str,
    author: str | None = None,
    created_at: Any = None,
    rating: int | None = None,
    thread_context: str | None = None,
    collect_query: str | None = None,
    text_available: bool = True,
    ingest_run_id: str,
) -> dict[str, Any] | None:
    """Map a source payload onto the `records` schema.

    Returns None for records that carry no text at all -- deleted/removed
    bodies with valid metadata (EC-COL-4). The caller logs those as
    `exclusions/deleted` rather than dropping them silently.
    """
    if text_raw is None or str(text_raw).strip() in DELETED_MARKERS:
        return None
    if not source_url:
        # NFR-1: no record without a traceable origin. This is not negotiable.
        raise ValueError(f"{source}/{native_id}: no source_url")

    raw = str(text_raw)
    return {
        "record_id": record_id(source, native_id),
        "source": source,
        "source_url": source_url,
        "native_id": str(native_id),
        "author_hash": author_hash(author),
        "created_at": to_iso(created_at),
        "text_raw": raw,                       # verbatim -- what the classifier reads
        "text_clean": _WS.sub(" ", raw).strip(),  # normalised copy, for matching/search
        "lang": None,                          # set by pipeline/clean/language.py
        "rating": rating,
        "thread_context": thread_context,
        "collect_query": collect_query,        # bias auditing -- EC-COL-12
        "text_available": 1 if text_available else 0,
        "collected_at": now_iso(),
        "ingest_run_id": ingest_run_id,
    }


COLUMNS = (
    "record_id", "source", "source_url", "native_id", "author_hash", "created_at",
    "text_raw", "text_clean", "lang", "rating", "thread_context", "collect_query",
    "text_available", "collected_at", "ingest_run_id",
)


def write_records(con: sqlite3.Connection, rows: Iterable[dict]) -> int:
    """Idempotent insert. Re-running a collector never duplicates."""
    rows = list(rows)
    if not rows:
        return 0
    con.executemany(
        f"INSERT OR IGNORE INTO records ({','.join(COLUMNS)}) "
        f"VALUES ({','.join('?' * len(COLUMNS))})",
        [tuple(r[c] for c in COLUMNS) for r in rows],
    )
    con.commit()
    return len(rows)


def log_exclusion(con: sqlite3.Connection, *, record_id_: str, source: str,
                  stage: str, reason: str, detail: str, run_id: str) -> None:
    con.execute(
        "INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason, detail, run_id)"
        " VALUES (?,?,?,?,?,?)",
        (record_id_, source, stage, reason, detail, run_id),
    )
