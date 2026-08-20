"""Numeral verification for generated prose.

Citations prove an insight POINTS AT a row. They do not prove the sentence
reports what the row says — "C2 leads at 41%" can cite the row that reads
23.7% and the citation resolves perfectly. So every numeral in a generated
statement is extracted and matched against the values of the rows it cites.

Built here rather than in P4 on purpose: implementationplan.md task 4.7 needs
exactly this check for the chatbot (S4-INV-2, absolute at 100%), and a verifier
that has already been run against real generated text is worth more at that
gate than one written the day it is needed.

THE STRUCTURAL-CONSTANT ALLOWLIST (EC-CHAT-10)
----------------------------------------------
Small integers appear in prose as ordinals and quantifiers — "the top three",
"both of the two leading codes" — not as claims about the corpus. Rejecting
them would make the check unusable and push generation toward vaguer sentences,
which is the opposite of the goal. They are allowed, and that is a real hole:
a fabricated "3 sources" passes. It is narrow, it is stated, and it is why
`n_sources`-style claims are checked by citation shape as well.
"""

from __future__ import annotations

import re

# 0-5 as bare integers only. "3.2x" or "3%" is a claim and is checked.
STRUCTURAL_CONSTANTS = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0}
TOLERANCE = 0.011          # 1.1pp — absorbs 23.7% vs 0.2367 rounding, not a wrong number

_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(%|x|×)?", re.I)


def numerals(text: str) -> list[tuple[float, str]]:
    """(value, suffix) for every number in the text. A trailing % is kept
    because 24 and 24% are different claims about the same row."""
    out = []
    for m in _NUM.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            out.append((float(raw), (m.group(2) or "").lower()))
        except ValueError:
            continue
    return out


def _candidates(rows: list[dict]) -> set[float]:
    """Every number a cited row can legitimately support, in every form the
    prose might reasonably render it: the raw value, its percentage, and both
    rounded the way a person writes them."""
    vals: set[float] = set()
    for row in rows:
        for v in row.values():
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)):
                f = float(v)
                vals.update({f, round(f, 1), round(f, 2), round(f, 3)})
                if 0.0 <= f <= 1.0:                     # a share, quoted as a percentage
                    vals.update({f * 100, round(f * 100, 1), round(f * 100, 2)})
                if f != 0:
                    vals.add(round(f))
    return vals


def check_numerals(statement: str, rows: list[dict]) -> list[str]:
    """Numbers in `statement` that no cited row supports. Empty list = clean."""
    if not rows:
        return [f"{v:g}{s}" for v, s in numerals(statement)]
    cands = _candidates(rows)
    bad = []
    for value, suffix in numerals(statement):
        if not suffix and value in STRUCTURAL_CONSTANTS:
            continue
        if any(abs(value - c) <= TOLERANCE for c in cands):
            continue
        # A share written as a percentage where the row stores the fraction,
        # or the reverse — both are the same claim about the same row.
        if any(abs(value / 100 - c) <= TOLERANCE / 100 for c in cands):
            continue
        bad.append(f"{value:g}{suffix}")
    return bad
