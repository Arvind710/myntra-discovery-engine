"""PII scrubbing (NFR-7) and length filtering.

EC-CLEAN-3: scrub to TYPED PLACEHOLDERS, never by deletion. An order id
inside a narrative is often load-bearing -- "order 12345 came in the wrong
size and now I don't trust the sizing" is a C7 record. Deleting the number
mangles the sentence; replacing it with [ORDER_ID] preserves the structure
the classifier reads.

`text_raw` is scrubbed in place because it is what leaves the machine (the
Data Bank is public). There is no unscrubbed copy anywhere.
"""

from __future__ import annotations

import re
import sqlite3

MIN_LENGTH = 15  # chars after normalisation (EC-COL-6)

PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    # Indian mobile numbers, with or without +91 / leading 0
    (re.compile(r"(?<!\d)(?:\+?91[\-\s]?|0)?[6-9]\d{9}(?!\d)"), "[PHONE]"),
    (re.compile(r"\b(?:order|ord|awb|tracking)[\s#:\-]*([A-Z0-9]{6,20})\b", re.I), "[ORDER_ID]"),
    (re.compile(r"\b\d{12,19}\b"), "[LONG_NUMBER]"),           # card-like
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN]"),          # Indian PAN
    (re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"), "[AADHAAR]"),
]

_EMOJI_ONLY = re.compile(
    r"^[\s←-⇿⌀-➿⬀-⯿\U0001F000-\U0001FAFF‍️]*$"
)
_WS = re.compile(r"\s+")


def scrub(text: str) -> tuple[str, list[str]]:
    """Return (scrubbed_text, kinds_found)."""
    found: list[str] = []
    out = text
    for pat, placeholder in PATTERNS:
        out, n = pat.subn(placeholder, out)
        if n:
            found.append(placeholder.strip("[]"))
    return out, found


def is_too_short(text: str) -> bool:
    return len(_WS.sub(" ", text).strip()) < MIN_LENGTH


def is_emoji_only(text: str) -> bool:
    return bool(_EMOJI_ONLY.match(text.strip()))


def run(con: sqlite3.Connection, run_id: str) -> dict[str, int]:
    stats = {"scrubbed": 0, "too_short": 0, "emoji_only": 0}
    rows = list(con.execute("SELECT record_id, source, text_raw FROM records"))

    for r in rows:
        raw = r["text_raw"]
        cleaned, kinds = scrub(raw)
        if kinds:
            con.execute(
                "UPDATE records SET text_raw=?, text_clean=? WHERE record_id=?",
                (cleaned, _WS.sub(" ", cleaned).strip(), r["record_id"]))
            stats["scrubbed"] += 1
            raw = cleaned

        if is_emoji_only(raw):
            reason, key = "length", "emoji_only"
        elif is_too_short(raw):
            reason, key = "length", "too_short"
        else:
            continue
        con.execute(
            "INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason, detail, run_id)"
            " VALUES (?,?,?,?,?,?)",
            (r["record_id"], r["source"], "clean", reason, key, run_id))
        stats[key] += 1

    con.commit()
    return stats
