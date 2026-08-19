"""Language tagging. METADATA ONLY -- never a reason to drop a record.

EC-CLEAN-4/5: a large share of the relevant Indian corpus is Hinglish or
code-mixed, and short Hinglish is exactly where automatic langid fails.
Dropping on a failed detection would silently remove the records the
project most needs. `unknown` is a valid value.

Hinglish is KEPT, NEVER TRANSLATED (arch §5.3): translation destroys the
verbatim evidence NFR-1 depends on, and `evidence_span` must remain an
exact substring of what the user actually wrote.
"""

from __future__ import annotations

import re
import sqlite3

# Function words that mark Hindi written in Latin script. Chosen to be
# common in speech and rare as English words.
HINGLISH_MARKERS = {
    "hai", "hain", "nahi", "nahin", "kya", "aur", "bhi", "yaar", "acha",
    "accha", "bohot", "bahut", "kar", "karo", "karna", "kiya", "mera",
    "meri", "tera", "apna", "mujhe", "tumhe", "hoga", "hota", "gaya",
    "raha", "rahi", "bas", "abhi", "phir", "pehle", "wala", "wali",
    "matlab", "kaise", "kyun", "kyu", "thoda", "zyada", "sahi", "galat",
    "paisa", "paise", "kabhi", "hamesha", "isliye", "lekin", "magar",
}

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
TAMIL = re.compile(r"[஀-௿]")
BENGALI = re.compile(r"[ঀ-৿]")
_WORD = re.compile(r"[a-z]+")


def detect(text: str) -> str:
    """en | hi | hi-Latn | mixed | other | unknown"""
    if not text or not text.strip():
        return "unknown"

    has_deva = bool(DEVANAGARI.search(text))
    has_latin = bool(re.search(r"[A-Za-z]", text))

    if TAMIL.search(text) or BENGALI.search(text):
        return "other"
    if has_deva and has_latin:
        return "mixed"
    if has_deva:
        return "hi"

    words = _WORD.findall(text.lower())
    if not words:
        return "unknown"
    hits = sum(1 for w in words if w in HINGLISH_MARKERS)
    # Two markers, or one in a short text, is enough. Precision matters
    # less than never dropping: `lang` is descriptive, not a gate.
    if hits >= 2 or (hits == 1 and len(words) <= 12):
        return "hi-Latn"
    return "en" if has_latin else "unknown"


def run(con: sqlite3.Connection, run_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in list(con.execute("SELECT record_id, text_raw FROM records")):
        lang = detect(r["text_raw"])
        con.execute("UPDATE records SET lang=? WHERE record_id=?", (lang, r["record_id"]))
        counts[lang] = counts.get(lang, 0) + 1
    con.commit()
    return counts
