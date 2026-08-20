"""Step 5 — the verifier. Every number and every quote checked against what
was actually retrieved (architecture.md §8.8).

THE DISTINCTION THAT MATTERS
----------------------------
These are post-generation checks in Python, not requests in a prompt. "Cite
your sources" is an instruction; a model that ignores it produces an answer
indistinguishable from one that obeyed. `check()` goes and looks. A model that
ignores the instruction still gets caught, which is the difference between a
guarantee and a hope — and it is why T-10 and T-11 can be absolute thresholds
rather than metrics with a tolerance band.

WHAT COUNTS AS SUPPORT
----------------------
A numeral is supported if it appears in a retrieved row — including inside the
TEXT of one. The registered method flags carry their numbers in prose ("kappa
0.10", "about 79%"), and an answer that repeats a caveat verbatim is quoting
retrieved evidence, not inventing a statistic. Restricting candidates to
numeric COLUMNS would reject exactly the caveats the answer contract makes
mandatory, and the pressure would then be to drop the caveat rather than fix
the checker — the checker making the answer worse.

THE KNOWN HOLE, STATED
----------------------
Bare integers 0-5 are exempt (they are ordinals and quantifiers — "the top
three"), as are the structural constants. So a fabricated "3 sources" passes.
It is narrow, it is inherited from the P3 verifier where the same trade-off was
taken deliberately, and it is why claims of that shape are also checked by
citation shape. Widening the check to reject "the top three" would make it
unusable and push generation toward vaguer prose, which is the opposite of the
goal.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The numeral machinery is REUSED from the insight verifier rather than
# rewritten. implementationplan.md task 4.7 asks for exactly this check, and a
# verifier already run in anger against real generated prose is worth more at
# this gate than one written the day it is needed.
from pipeline.synthesise.verify import (  # noqa: E402
    STRUCTURAL_CONSTANTS, TOLERANCE, numerals,
)

from lib.charts import MIN_N_RANKED, MIN_N_VISIBLE  # noqa: E402

# Corpus share is share of DISCUSSION. This regex is shared with insight
# generation so the same phrasing is forbidden in an insight and in an answer;
# a rule enforced in one output and not the other is a rule with a hole.
FUNNEL_LANGUAGE = re.compile(
    r"\b(drop[- ]?off|drop out|conversion rate|convert(?:s|ed)? at|abandon(?:ment)? rate|"
    r"of (?:all )?users (?:who|that)|of shoppers (?:who|that)|churn(?:ed)? at|"
    r"funnel (?:rate|loss)|purchase rate)\b", re.I)

# `[[table|key]]` for an analysis row, `[[rec|record_id]]` for a record.
# Double brackets so the form cannot collide with a markdown link.
CITATION = re.compile(r"\[\[([a-z_]+)\|([^\]]+)\]\]")

QUOTE = re.compile(r"[\"“]([^\"“”]{3,400})[\"”]")

REQUIRED_SECTIONS = ("Confidence", "Limitations")

# Structural constants beyond the inherited 0-5 (EC-CHAT-10). Deliberately
# short: every entry is a number about the INSTRUMENT rather than a finding,
# and each one added is a small hole punched in T-10.
def structural_constants(n_codes: int = 34) -> set[float]:
    return set(STRUCTURAL_CONSTANTS) | {
        float(n_codes),          # size of the codebook
        float(MIN_N_VISIBLE),    # the two reporting floors
        float(MIN_N_RANKED),
        0.6, 0.60,               # the kappa threshold, quoted as a target
        2000.0,                  # the corpus size target from the plan
    }


# Cues that the funnel word is being DENIED rather than asserted. Without this
# the check fires on the answer contract's own mandatory caveat — "every share
# here is a share of discussion, never a drop-off rate" — and the cheapest way
# to satisfy a checker that punishes the disclaimer is to delete the disclaimer.
# A rule that makes the answer worse is a broken rule, not a strict one.
_NEGATION = re.compile(
    r"\b(not|never|no|cannot|can't|isn't|aren't|rather than|instead of|"
    r"does not|do not|is not|are not|without)\b", re.I)


def _negated(text: str, start: int, window: int = 70) -> bool:
    """Look back for a denial, but never past the start of the sentence.

    An unclipped window reads the previous sentence's "never" as licence for
    this sentence's assertion — so a correct caveat in the Limitations section
    would excuse a genuine funnel claim two lines later. The negation has to
    govern the clause it appears in.
    """
    before = text[max(0, start - window):start]
    cut = max(before.rfind("."), before.rfind("\n"), before.rfind(";"),
              before.rfind("!"), before.rfind("?"))
    return bool(_NEGATION.search(before[cut + 1:] if cut >= 0 else before))


def _norm(s: str) -> str:
    """Whitespace- and case-normalised, with the quote characters unified.
    EC-CHAT-11: a valid quote must not be rejected because a curly apostrophe
    became a straight one on the way through a model."""
    s = str(s).replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def _candidate_numbers(rows: list[dict]) -> set[float]:
    """Every number a retrieved row can legitimately support, in every form
    prose might render it — the raw value, its percentage, the rounded forms a
    person actually writes, and any number embedded in a text column."""
    vals: set[float] = set()
    for row in rows or []:
        for k, v in row.items():
            if str(k).startswith("_"):
                continue
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)):
                f = float(v)
                vals.update({f, round(f, 1), round(f, 2), round(f, 3)})
                if 0.0 <= f <= 1.0:                    # a share, quoted as a percentage
                    vals.update({f * 100, round(f * 100, 1), round(f * 100, 2)})
                if f != 0:
                    vals.add(round(f))
            elif isinstance(v, str):
                for value, _suffix in numerals(v):
                    vals.update({value, round(value, 1), round(value, 2)})
                    if 0.0 <= value <= 1.0:
                        vals.update({value * 100, round(value * 100, 1)})
    return vals


def strip_citations(text: str) -> str:
    """Remove citation markers before reading the prose.

    Record ids are hex, and a hex id beginning `653385bf…` was extracted as the
    number 653385 and reported as an invented statistic. Citations are
    machinery, not claims: the checker should read what the sentence SAYS, and
    the citation's own correctness is `check_citations`'s job.
    """
    return CITATION.sub(" ", text or "")


def check_numerals(text: str, rows: list[dict], n_codes: int = 34) -> list[str]:
    """Numbers in `text` that no retrieved row supports. Empty list = clean."""
    allow = structural_constants(n_codes)
    cands = _candidate_numbers(rows)
    bad = []
    for value, suffix in numerals(strip_citations(text)):
        if not suffix and value in allow:
            continue
        if 1900 <= value <= 2100 and not suffix and value == int(value):
            continue                                    # a year, not a claim
        if any(abs(value - c) <= TOLERANCE for c in cands):
            continue
        # A share written as a percentage where the row stores the fraction, or
        # the reverse. Both are the same claim about the same row.
        if any(abs(value / 100 - c) <= TOLERANCE / 100 for c in cands):
            continue
        bad.append(f"{value:g}{suffix}")
    return bad


def _quotable_texts(records: list[dict], rows: list[dict]) -> list[str]:
    """Everything a quotation mark may legitimately enclose.

    Records first — that is what "In users' words" means. Analysis rows are
    included because a cluster label, an insight statement or a registered
    caveat is also retrieved text, and quoting one is reporting evidence rather
    than inventing testimony.
    """
    out: list[str] = []
    for r in records or []:
        for k in ("text_raw", "text_clean", "_span"):
            if r.get(k):
                out.append(_norm(r[k]))
    for row in rows or []:
        for k, v in (row or {}).items():
            if not str(k).startswith("_") and isinstance(v, str) and len(v) > 12:
                out.append(_norm(v))
    return out


def check_quotes(text: str, records: list[dict], rows: list[dict]) -> list[str]:
    """Quoted strings that are not an exact (normalised) substring of anything
    retrieved. T-11 / S4-INV-3, absolute.

    Quotes shorter than three words are exempt: they are terminology
    ("wishlist", "Defer") rather than testimony, and rejecting them would
    forbid the answer from naming its own vocabulary.
    """
    haystack = _quotable_texts(records, rows)
    bad = []
    for m in QUOTE.finditer(text or ""):
        q = _norm(m.group(1))
        if len(q.split()) < 3:
            continue
        # A trailing placeholder marks a phrase being NAMED rather than quoted —
        # "the counterfactual signal (I would have bought if…)". The exemption is
        # narrow on purpose and it is safe for the reason the check exists: the
        # danger of a fabricated quote is that it passes as testimony, and a
        # phrase ending in an ellipsis or a bare X cannot. Anything that reads
        # as something a person actually said is still checked.
        if re.search(r"(…|\.\.\.|\b[XY])\s*$", q.rstrip()):
            continue
        if any(q in h for h in haystack):
            continue
        bad.append(m.group(1)[:80])
    return bad


def citations(text: str) -> list[dict]:
    return [{"table": t, "key": k.strip()} for t, k in CITATION.findall(text or "")]


def check_citations(text: str, retrieved: list[dict], records: list[dict]) -> list[str]:
    """Every citation must point at something that was ACTUALLY RETRIEVED — not
    merely at a row that exists.

    That is the stricter of the two available checks and the right one here. A
    citation resolving to a real row the channels never returned means the model
    supplied the reference from its own reading of the corpus, which is the
    failure mode this whole design exists to make impossible.
    """
    available = {(r["_cite"]["table"], str(r["_cite"]["key"]))
                 for r in (retrieved or []) if r.get("_cite")}
    available |= {("record", str(r["record_id"])) for r in (records or [])
                  if r.get("record_id")}
    bad = []
    for c in citations(text):
        table = "record" if c["table"] in ("rec", "record") else c["table"]
        if (table, c["key"]) not in available:
            bad.append(f"{c['table']}[{c['key']}] was not retrieved")
    return bad


def _units(text: str) -> list[str]:
    """The blocks that must each carry a citation.

    A bullet is its own unit rather than part of its block. One citation at the
    foot of a six-bullet list would satisfy a per-paragraph rule while leaving
    five claims uncited, and a list is exactly where an answer puts its claims.
    """
    units: list[str] = []
    for block in re.split(r"\n\s*\n", text or ""):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        bullets = [ln for ln in lines if re.match(r"\s*(?:[-*•]|\d+\.)\s+", ln)]
        rest = [ln for ln in lines if ln not in bullets]
        # A bullet with more-indented bullets beneath it is a LABEL for them,
        # not a claim of its own — the numbers and their citations live in the
        # leaves. Flattening the list threw that structure away and demanded a
        # citation on "Mentions and distinct authors", which asserts nothing.
        parents = set()
        for i, ln in enumerate(lines):
            if ln not in bullets:
                continue
            indent = len(ln) - len(ln.lstrip())
            for nxt in lines[i + 1:]:
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent <= indent:
                    break
                if nxt in bullets:
                    parents.add(ln)
                    break
        bullets = [ln for ln in bullets if ln not in parents]
        # A block introduced by `Interpretation:` is inference throughout —
        # the marker is on the introducing line and the bullets under it are
        # the same thought continued. Requiring the prefix on every bullet
        # would demand the word six times in a row to say one thing.
        inherited = any(ln.strip().lower().lstrip("*_-• ").startswith("interpretation:")
                        for ln in rest)
        if bullets:
            units.extend((f"Interpretation: {b}" if inherited else b) for b in bullets)
            if rest:
                units.append(" ".join(rest))
        else:
            units.append(" ".join(lines))
    return units


def _is_structural(unit: str) -> bool:
    """Headings, section labels and empty scaffolding carry no claim and need
    no citation. A line is structural if stripping markdown emphasis and a
    trailing colon leaves nothing but a short label."""
    u = unit.strip()
    if u.startswith("#"):
        return True
    bare = re.sub(r"[*_`>\-•]", "", u).strip()
    # A line ending in a colon INTRODUCES the lines beneath it; the claim and
    # its citation live in those. Length was the wrong test — "Largest shares
    # of discussion by code (overall; all are Stage C):" is a label by
    # function, not by brevity, and demanding a citation on it forces one onto
    # a line that asserts nothing.
    if bare.endswith(":"):
        return True
    return len(bare.split()) <= 3


def check_uncited(text: str) -> list[str]:
    """Units carrying a claim with neither a citation nor an `Interpretation:`
    prefix. S4-INV-5.

    `Interpretation:` is not a loophole — it is the contract. The boundary
    between what the data says and a reading of the data is the one thing a
    PM must be able to see at a glance, so a sentence is allowed to be
    uncited exactly when it announces that it is inference.
    """
    bad = []
    for unit in _units(text):
        if _is_structural(unit):
            continue
        stripped = re.sub(r"^\s*(?:[-*•]|\d+\.)\s*", "", unit).strip()
        stripped = re.sub(r"^[*_]+", "", stripped)
        if stripped.lower().startswith("interpretation:"):
            continue
        if CITATION.search(unit):
            continue
        bad.append(unit.strip()[:100])
    return bad


@dataclass
class Report:
    """The verifier's finding. `ok` is the whole gate; the named lists are what
    a regeneration prompt is built from and what the eval asserts on."""
    ok: bool = True
    bad_numerals: list[str] = field(default_factory=list)      # S4-INV-2 / T-10
    bad_quotes: list[str] = field(default_factory=list)        # S4-INV-3 / T-11
    bad_citations: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)  # S4-INV-4
    uncited: list[str] = field(default_factory=list)           # S4-INV-5
    missing_evidence: list[str] = field(default_factory=list)  # S4-INV-6
    scope_violations: list[str] = field(default_factory=list)  # S4-INV-7
    proxy_violations: list[str] = field(default_factory=list)  # S4-INV-8

    def problems(self) -> list[str]:
        out = []
        for label, items in (
                ("unsupported number", self.bad_numerals),
                ("unverifiable quote", self.bad_quotes),
                ("citation not retrieved", self.bad_citations),
                ("missing section", self.missing_sections),
                ("uncited claim", self.uncited),
                ("missing evidence type", self.missing_evidence),
                ("out-of-scope claim", self.scope_violations),
                ("share stated as a funnel measure", self.proxy_violations)):
            out += [f"{label}: {x}" for x in items]
        return out


def check(answer: str, route: str, retrieved_rows: list[dict],
          retrieved_records: list[dict], *, n_codes: int = 34) -> Report:
    """Run every post-generation check. `retrieved_rows` is every citable
    analysis row from any channel; `retrieved_records` is every record."""
    rep = Report()
    text = answer or ""

    rep.bad_numerals = check_numerals(text, retrieved_rows, n_codes)
    rep.bad_quotes = check_quotes(text, retrieved_records, retrieved_rows)
    rep.bad_citations = check_citations(text, retrieved_rows, retrieved_records)

    rep.proxy_violations = [m.group(0) for m in FUNNEL_LANGUAGE.finditer(text)
                            if not _negated(text, m.start())]

    if route == "NONE":
        # A refusal states what the engine does not cover. It must not slip in
        # a corpus fact on the way out — that is the failure that makes a
        # refusal worse than useless, because it looks like restraint.
        cites = citations(text)
        if cites:
            rep.scope_violations = [f"cites {c['table']}[{c['key']}] in a refusal"
                                    for c in cites]
        stray = check_numerals(text, [], n_codes)
        if stray:
            rep.scope_violations += [f"states {s} with no evidence behind it"
                                     for s in stray]
    else:
        rep.missing_sections = [s for s in REQUIRED_SECTIONS
                                if s.lower() not in text.lower()]
        rep.uncited = check_uncited(text)
        if route == "FULL":
            cited = citations(text)
            if not any(c["table"] in ("rec", "record") for c in cited):
                rep.missing_evidence.append("no record cited — a FULL answer must "
                                            "quote at least one primary source")
            if not any(c["table"].startswith("analysis_") or c["table"] in
                       ("cluster_labels", "insights", "hypotheses") for c in cited):
                rep.missing_evidence.append("no analysis row cited — a FULL answer "
                                            "must rest on at least one counted result")

    rep.ok = not rep.problems()
    return rep
