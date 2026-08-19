"""Translate engine codes into the updated framework's codes.

Single choke point. The framework RENUMBERS Stage C — engine C9 is framework
C10, engine C10 is framework C4.5 — so a page that maps a code inline would
eventually render a number under a label that means something else. Every
display path goes through here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def crosswalk() -> dict:
    return yaml.safe_load((ROOT / "codebook" / "crosswalk_v2.yaml").read_text())


@lru_cache(maxsize=256)
def to_framework(code: str) -> str:
    m = crosswalk()["engine_to_framework"].get(code)
    return m["to"] if m else code          # Stage A/B/D are unchanged


@lru_cache(maxsize=256)
def name_of(code: str) -> str:
    fw = to_framework(code)
    root = fw.split(".")[0]
    spec = crosswalk()["stage_c"].get(root)
    if spec:
        return spec.get("name", "")
    return {
        "A1.1": "No trigger to return", "A1.2": "No change signal",
        "A1.3": "Save never encoded as a decision",
        "A2.1": "Wishlist entry point buried", "A2.2": "Cross-device / logged-out saves",
        "A3.1": "Static list, no new information", "A3.2": "Re-entry via search or feed",
        "B1.1": "No search/filter/sort in wishlist", "B1.2": "Reverse-chronological only",
        "B1.3": "Undifferentiated grid", "B2.1": "Out-of-stock clutter",
        "B2.2": "Delisted products", "B2.3": "Duplicate saves",
        "B3.1": "Save context not captured", "B3.2": "Variant not preserved",
        "D1": "Cost surprise", "D2": "Mechanical friction",
        "D3": "Late-revealed terms", "D4": "Final reconsideration",
        "S14": "Action trigger (journey stage)",
        "Z-99": "Residual — relevant but uncoded",
    }.get(fw, "")


def translation_note(code: str) -> str:
    m = crosswalk()["engine_to_framework"].get(code)
    if not m:
        return ""
    note = str(m.get("note", ""))
    return "" if note == "direct" else note


def subcode_label(theme: str, subcode: str) -> str:
    spec = crosswalk()["stage_c"].get(theme, {})
    return (spec.get("subcodes") or {}).get(subcode, "no specific sub-code")


SEGMENTS = {
    1: ("Collectors", "No purchase intent — correct behaviour, not addressable"),
    2: ("Lapsed Intenders", "Intent existed and lapsed — desire cooled, bought elsewhere"),
    3: ("Ready Buyers", "Intent, soon, decided — nothing unresolved"),
    4: ("Stuck Deciders", "Intent, soon, NOT decided — an unresolved doubt is blocking"),
    5: ("Committed Waiters", "Intent, later, decided — waiting on a condition"),
    6: ("Hesitant Waiters", "Intent, later, not decided"),
}
TARGET_SEGMENT = 4
