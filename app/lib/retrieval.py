"""The five retrieval channels and the answerability gate — steps 2 and 3 of
the analyst loop (architecture.md §8.4, §8.5).

NOT ONE LINE OF THIS FILE CALLS A MODEL, AND THAT IS THE DESIGN
---------------------------------------------------------------
Ordinary RAG embeds the question, pulls the nearest chunks, and asks a model to
write something over them. Every property you would want — that the numbers are
real, that the refusal is honest, that counter-evidence was looked for — is then
a property of the prompt, which is to say a hope.

Here the model chooses *which* whitelisted query to run and with what arguments.
It never writes SQL, never sees a table it was not handed, and never decides
whether it has enough evidence to answer. Those are all decided in this file, in
Python, by code that can be unit-tested without an API key. The consequence is
that `gate()` returning NONE is a fact about the retrieval, not an instruction
the model complied with — which is exactly what makes AC-4 testable.

THE FIVE CHANNELS
-----------------
1. Structured facts — whitelisted, parameterised SQL over the `analysis_*`
   tables. The channel that makes quantitative honesty possible: the model is
   handed `{code: C1, n: 241, denominator: 1018, share: 0.237}` and must quote
   it, rather than reading "many users" in a passage and writing "about a third".
2. Verbatim evidence — BM25 over the labelled corpus, FILTERED BY CODE. The
   corpus is already classified, so "fit-uncertainty quotes" is an exact filter
   rather than a similarity guess.
3. Disconfirming evidence — retrieves AGAINST the emerging answer. Rival codes,
   complicating co-occurrences, and the unclassified residual. Almost nothing
   does this, and it is the difference between a system that confirms and one
   that investigates (R-1).
4. Method and limitations — source mix, classifier agreement, and the registered
   bias flags for the codes in play. This is what lets Confidence and
   Limitations be DERIVED rather than performed.
5. External corroboration — the curated research sub-corpus, so an answer can
   say where the corpus agrees with published work and, more usefully, where it
   does not.

WHY THE POOL IS `relevance.is_relevant=1 AND retained`
------------------------------------------------------
That is 1,018 records, and 1,018 is the denominator every share in
`analysis_*` was computed against. A quote drawn from outside it would be
evidence for a claim whose percentage excluded that very record — a small
inconsistency that is impossible to spot in a finished answer and impossible to
defend once spotted.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from lib import db as appdb

# The minimum-n floor is IMPORTED, never redeclared. implementationplan.md 2.15
# requires charts and chatbot to use the same one; two constants that agree
# today are two constants that can disagree after one edit, and the failure
# would show up as a chart and an answer quietly disagreeing about whether a
# barrier is rankable.
from lib.charts import MIN_N_RANKED, MIN_N_VISIBLE

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The citation contract is shared with insight generation rather than reinvented:
# one shape for a citation across the whole project means the checker has one
# path to test and a reader sees the same reference format everywhere.
from pipeline.synthesise.citations import CITABLE  # noqa: E402

# The pool every number and every quote is drawn from. See the module note.
POOL = ("SELECT r.* FROM records r "
        "JOIN relevance v ON v.record_id = r.record_id AND v.is_relevant = 1 "
        "JOIN retained t ON t.record_id = r.record_id")


# ---------------------------------------------------------------------------
# Channel 1 — the whitelisted query registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Spec:
    """One query the planner is allowed to ask for.

    `describe` is not documentation — it is the text the planner reads when it
    chooses. A vague description produces a wrong choice, and a wrong choice is
    the one failure mode this design cannot catch downstream: the numbers will
    be real, and about the wrong thing.
    """
    describe: str
    args: tuple[str, ...]
    table: str                      # for the citation key; "" = not citable
    build: Callable[[dict], tuple[str, tuple]]
    kinds: tuple[str, ...] = ()     # evidence-requirement kinds this satisfies


def _in_clause(col: str, values: list[str]) -> tuple[str, list]:
    """Parameterised IN. The values are still bound, never interpolated — the
    only thing derived from user-influenced data is the NUMBER of `?`."""
    vals = [str(v) for v in (values or [])]
    if not vals:
        return ("1=1", [])
    return (f"{col} IN ({','.join('?' * len(vals))})", vals)


# One normaliser for every path a code string can arrive by — the planner's
# entities, the planner's query arguments, and the auto-fulfilled queries.
# When only `plan_codes` parsed labels, the gate knew the question was about C1
# while the SQL still looked up "C1 (fit & size uncertainty)" and found nothing.
_CODE_TOKEN = re.compile(r"\s*(Z-?99|[A-D]\d+(?:\.\d+)?|[A-D])\b", re.I)


def norm_code(raw) -> str | None:
    """"C1 (fit & size uncertainty)" -> "C1". A bare stage letter -> None."""
    m = _CODE_TOKEN.match(str(raw).strip())
    if not m:
        return None
    code = m.group(1).upper()
    if re.fullmatch(r"[A-D]", code):
        return None
    return "Z-99" if code.replace("-", "") == "Z99" else code


def _codes(a: dict) -> list[str]:
    out = [norm_code(c) for c in (a.get("codes") or [])]
    return list(dict.fromkeys(c for c in out if c))


def _code_filter(a: dict) -> tuple[str, list]:
    """The WHERE clause for a code argument.

    Distinguishes "no codes requested" from "codes requested, none of them
    valid". `_in_clause` alone treats both as no filter, so a request for
    specific codes whose values normalised to nothing came back as ALL
    thirty-four — a question about one barrier answered with the whole
    codebook. Asking for nothing valid must return nothing.
    """
    requested = a.get("codes") or []
    codes = _codes(a)
    if requested and not codes:
        return ("1=0", [])
    return _in_clause("code", codes)


def _limit(a: dict, default: int = 10, cap: int = 34) -> int:
    """0 and absent both mean "use the default". The planner emits a fixed
    argument shape with every field present, so an unused `limit` arrives as 0
    — and clamping that to 1 would silently return a single row for a question
    that asked for a ranking."""
    try:
        v = int(a.get("limit") or 0)
    except (TypeError, ValueError):
        return default
    return default if v <= 0 else min(v, cap)


QUERIES: dict[str, Spec] = {

    "code_prevalence": Spec(
        describe=("How often each named barrier is raised: n records, n distinct "
                  "authors, the denominator, share of relevant discussion, how many "
                  "sources it appears in, mean classifier confidence. THE default "
                  "quantitative query. Use whenever a question asks how big, how "
                  "common, or how often."),
        args=("codes",), table="analysis_code_prevalence", kinds=("prevalence",),
        build=lambda a: (
            (lambda w: (f"SELECT * FROM analysis_code_prevalence WHERE {w[0]} "
                        "ORDER BY n DESC", tuple(w[1])))(_code_filter(a)))),

    "top_codes": Spec(
        describe=("The barriers ranked by how much of the relevant discussion they "
                  "account for, most-raised first. Optionally within one journey "
                  "stage (A, B, C or D). Use for 'what are the biggest reasons', "
                  "'top barriers', or any open ranking question."),
        args=("stage", "limit"), table="analysis_code_prevalence",
        kinds=("prevalence", "ranking"),
        build=lambda a: (
            ("SELECT * FROM analysis_code_prevalence WHERE stage = ? "
             "ORDER BY n DESC LIMIT ?", (str(a["stage"]).upper()[:1], _limit(a)))
            if a.get("stage") else
            ("SELECT * FROM analysis_code_prevalence ORDER BY n DESC LIMIT ?",
             (_limit(a),)))),

    "stage_outcome": Spec(
        describe=("Share of discussion per journey stage (A discovery/recall, "
                  "B browsing, C item decision, D checkout) crossed with outcome "
                  "(Exit = abandoned for good, Defer = postponed with intent "
                  "surviving). Use for 'where in the journey', 'which stage', or "
                  "any question about postponement versus abandonment."),
        args=(), table="analysis_stage_outcome", kinds=("outcome", "stage"),
        build=lambda a: ("SELECT * FROM analysis_stage_outcome ORDER BY stage, outcome", ())),

    "source_breakdown": Spec(
        describe=("Per-source counts and shares for the named barriers, with the "
                  "Jensen-Shannon divergence measuring how unevenly the barrier is "
                  "distributed across sources. Use to test whether a finding is one "
                  "platform's artefact -- ALWAYS pull this for a comparison or a "
                  "ranking claim."),
        args=("codes",), table="analysis_source_code", kinds=("source_breakdown",),
        build=lambda a: (
            (lambda w: (f"SELECT * FROM analysis_source_code WHERE {w[0]} "
                        "ORDER BY code, n DESC", tuple(w[1])))(_code_filter(a)))),

    "segment_breakdown": Spec(
        describe=("Barrier prevalence within each user segment. Segments are a "
                  "re-cut of the item-decision stage by whether the shopper has "
                  "decided and how urgent the need is. Use for 'which users', "
                  "'does this differ by segment', or a targeting question."),
        args=("codes", "segment_id"), table="analysis_segment_code_v2",
        kinds=("segment_split",),
        build=lambda a: (
            (lambda w: ((f"SELECT * FROM analysis_segment_code_v2 WHERE {w[0]} "
                         "AND segment_id = ? ORDER BY n DESC",
                         tuple(w[1]) + (int(a["segment_id"]),))
                        if str(a.get("segment_id", "")).strip() not in ("", "None")
                        else (f"SELECT * FROM analysis_segment_code_v2 WHERE {w[0]} "
                              "ORDER BY segment_id, n DESC", tuple(w[1])))
             )(_code_filter(a)))),

    "segment_recommendation": Spec(
        describe=("The segments with size, share, the barriers most distinctive to "
                  "each, and which one the analysis recommends targeting, with its "
                  "rationale. Use for 'who should we build for'."),
        args=(), table="analysis_segment_recommendation", kinds=("segment_split", "recommendation"),
        build=lambda a: ("SELECT * FROM analysis_segment_recommendation ORDER BY score DESC", ())),

    "cooccurrence": Spec(
        describe=("Barrier pairs that appear together in the same record, with lift "
                  "and PMI above a minimum-support floor. Use for 'do these go "
                  "together', compound barriers, or 'what else is going on when X "
                  "is raised'."),
        args=("codes",), table="analysis_cooccurrence", kinds=("cooccurrence",),
        build=lambda a: (
            (lambda cs: (("SELECT * FROM analysis_cooccurrence WHERE min_support_met = 1 "
                          f"AND (code_a IN ({','.join('?' * len(cs))}) OR "
                          f"code_b IN ({','.join('?' * len(cs))})) "
                          "ORDER BY lift DESC LIMIT 15", tuple(cs) + tuple(cs))
                         if cs else
                         ("SELECT * FROM analysis_cooccurrence WHERE min_support_met = 1 "
                          "ORDER BY lift DESC LIMIT 15", ())))(_codes(a)))),

    "opportunity": Spec(
        describe=("The opportunity ranking: six scored components (how often it "
                  "comes up, how hard people work around it, how often intent "
                  "survives, whether it is fixable without a discount, how "
                  "well-supported it is, how specific it is to the target segment), "
                  "the composite score and rank. Use for 'what should we solve', "
                  "'what is the biggest opportunity'."),
        args=("codes", "limit"), table="analysis_opportunity",
        kinds=("opportunity", "ranking"),
        build=lambda a: (
            (lambda w, cs: (f"SELECT * FROM analysis_opportunity WHERE {w[0]} "
                            "ORDER BY score DESC" + ("" if cs else " LIMIT ?"),
                            tuple(w[1]) if cs else (_limit(a),))
             )(_code_filter(a), _codes(a)))),

    "evidence_strength": Spec(
        describe=("How well-supported each barrier is, decomposed into prevalence, "
                  "source diversity, counterfactual rate, workaround rate, mean "
                  "classifier confidence and recency, plus the composite. Use when "
                  "asked how confident we are, or how solid a finding is."),
        args=("codes",), table="analysis_evidence_strength", kinds=("confidence",),
        build=lambda a: (
            (lambda w: (f"SELECT * FROM analysis_evidence_strength WHERE {w[0]} "
                        "ORDER BY composite DESC", tuple(w[1])))(_code_filter(a)))),

    "counterfactuals": Spec(
        describe=("How often people state they WOULD have bought if the barrier were "
                  "removed -- an explicit conditional-purchase signal, not an "
                  "inference. Use for 'would they buy if', 'is this actually "
                  "blocking a sale'."),
        args=("codes",), table="analysis_counterfactuals", kinds=("counterfactual",),
        build=lambda a: (
            (lambda w: (f"SELECT * FROM analysis_counterfactuals WHERE {w[0]} "
                        "ORDER BY share DESC", tuple(w[1])))(_code_filter(a)))),

    "workaround": Spec(
        describe=("How often people describe doing extra work to get around a "
                  "barrier, and how much effort it costs them. A high rate means "
                  "the need survives the obstacle. Use for intensity, 'how much does "
                  "it bother them', 'what do they do instead'."),
        args=("codes",), table="analysis_workaround", kinds=("intensity",),
        build=lambda a: (
            (lambda w: (f"SELECT * FROM analysis_workaround WHERE {w[0]} "
                        "ORDER BY share DESC", tuple(w[1])))(_code_filter(a)))),

    "addressable": Spec(
        describe=("The sizing of what was deliberately EXCLUDED from the addressable "
                  "opportunity -- people who never intended to buy, and people using "
                  "the wishlist as a reference shelf -- and what remains. Use for "
                  "'how big is the real opportunity'."),
        args=(), table="analysis_addressable", kinds=("addressable",),
        build=lambda a: ("SELECT * FROM analysis_addressable ORDER BY n DESC", ())),

    "stage_inversion": Spec(
        describe=("How far each journey stage would have to be under-reported in "
                  "this corpus before it overtook the leading stage. Turns the known "
                  "Stage A blind spot into a number. Use for 'how confident are you "
                  "in the stage ranking', 'what about the silent barriers'."),
        args=(), table="analysis_stage_inversion", kinds=("bias", "stage"),
        build=lambda a: ("SELECT * FROM analysis_stage_inversion ORDER BY n DESC", ())),

    "subcodes": Spec(
        describe=("Sub-themes within a barrier -- what the barrier is actually ABOUT "
                  "at a finer grain, e.g. which specific doubt drives the "
                  "price/value barrier. Themes are code ids. Use when a question "
                  "asks what SORT of doubt or what SPECIFICALLY."),
        args=("theme",), table="analysis_subcode", kinds=("subcode",),
        build=lambda a: (
            ("SELECT * FROM analysis_subcode WHERE theme = ? ORDER BY n DESC",
             (str(a["theme"]).upper(),)) if a.get("theme") else
            ("SELECT * FROM analysis_subcode ORDER BY n DESC LIMIT ?", (_limit(a, 20),)))),

    "cluster_reconciliation": Spec(
        describe=("Where the blind machine-discovered clusters line up with the "
                  "hand-written codebook and where they do not. A cluster with no "
                  "dominant code is territory the codebook may have missed. Use for "
                  "'did you find anything you were not looking for'."),
        args=("codes",), table="analysis_cluster_code", kinds=("cluster", "novelty"),
        build=lambda a: (
            (lambda w: (f"SELECT * FROM analysis_cluster_code WHERE {w[0]} "
                        "ORDER BY n DESC LIMIT 20", tuple(w[1])))(_code_filter(a)))),

    "cluster_labels": Spec(
        describe=("The labels given to the machine-discovered clusters by a model "
                  "that was NOT shown the codebook, with their sizes. Use for "
                  "'what themes emerged on their own'."),
        args=("space",), table="cluster_labels", kinds=("cluster", "novelty"),
        build=lambda a: (
            ("SELECT * FROM cluster_labels WHERE space = ? ORDER BY size DESC",
             (str(a["space"]),)) if a.get("space") else
            ("SELECT * FROM cluster_labels ORDER BY size DESC", ()))),

    "insights": Spec(
        describe=("The generated insights, each with its 'so what' and whether it "
                  "was confirmed novel against the 28 pre-registered hypotheses. Use "
                  "for 'what did you find', 'anything surprising'."),
        args=("novelty",), table="", kinds=("insight",),
        build=lambda a: (
            ("SELECT * FROM insights WHERE novelty = ? ORDER BY n DESC",
             (str(a["novelty"]),)) if a.get("novelty") else
            ("SELECT * FROM insights ORDER BY n DESC", ()))),

    "hypotheses": Spec(
        describe=("The hypotheses, each with supporting count, source diversity, "
                  "confidence, contradicting evidence, and WHAT WOULD DISPROVE IT. "
                  "Use for 'what should we test', 'what is the hypothesis'."),
        args=("codes",), table="", kinds=("hypothesis",),
        build=lambda a: (
            (lambda cs: (("SELECT * FROM hypotheses WHERE " +
                          " OR ".join(["codes LIKE ?"] * len(cs)) +
                          " ORDER BY supporting_n DESC", tuple(f"%{c}%" for c in cs))
                         if cs else
                         ("SELECT * FROM hypotheses ORDER BY supporting_n DESC", ())))(_codes(a)))),

    "weight_sensitivity": Spec(
        describe=("How robust the opportunity ranking is: over 1,000 random "
                  "re-weightings, how often each barrier holds the top spot and its "
                  "rank spread. Use for 'why those weights', 'does the ranking "
                  "survive different priorities'."),
        args=("codes",), table="analysis_weight_sensitivity", kinds=("robustness",),
        build=lambda a: (
            (lambda w: (f"SELECT * FROM analysis_weight_sensitivity WHERE {w[0]} "
                        "ORDER BY top_share DESC", tuple(w[1])))(_code_filter(a)))),

    "gold_agreement": Spec(
        describe=("How well the classifier agreed with the human coder on each "
                  "barrier -- gold count, agreement, Cohen's kappa, and a verdict of "
                  "reliable / weak / unreliable / not measurable, with the caveat an "
                  "answer must carry. Use for any question about accuracy, "
                  "reliability, or how much to trust a specific code."),
        args=("codes",), table="analysis_gold_agreement", kinds=("reliability",),
        build=lambda a: (
            (lambda w: (f"SELECT * FROM analysis_gold_agreement WHERE {w[0]} "
                        "ORDER BY gold_n DESC", tuple(w[1])))(_code_filter(a)))),

    "method_flags": Spec(
        describe=("The registered method and bias flags -- what this corpus "
                  "structurally cannot show. Retrieved automatically for every "
                  "answer; you do not normally need to request it."),
        args=(), table="analysis_method_flags", kinds=("method",),
        build=lambda a: ("SELECT * FROM analysis_method_flags ORDER BY severity, flag_id", ())),

    "relevant_composition": Spec(
        # THE DEFAULT, and it must come first in the registry so `composition`
        # resolves here. A question asking how many records there are means the
        # ANALYSED pool — the 1,018 every share in every other table is computed
        # against. Answering it from the retained corpus reported YouTube at
        # 2,369 and called them relevant records, which is a different
        # population and a false statement about this one.
        describe=("How many RELEVANT records — the analysed pool that every share "
                  "and denominator in this project is computed against — with the "
                  "total, the distinct authors, and the split per source. THE "
                  "default for 'how many records', 'how big is the corpus', 'how "
                  "many people'."),
        args=(), table="", kinds=("composition",),
        build=lambda a: (
            "SELECT r.source, count(*) AS n, "
            "count(DISTINCT r.author_hash) AS authors, "
            "(SELECT count(*) FROM records r2 JOIN relevance v2 "
            "  ON v2.record_id=r2.record_id AND v2.is_relevant=1 "
            "  JOIN retained t2 ON t2.record_id=r2.record_id) AS total_relevant "
            f"FROM ({POOL}) r GROUP BY r.source ORDER BY n DESC", ())),

    "collected_composition": Spec(
        # Byte-identical to the Data Bank's own composition query, deliberately.
        # Two spellings of "records per source" is one spelling too many.
        describe=("How many records were COLLECTED and retained per source, before "
                  "the relevance filter — a much larger number than the analysed "
                  "pool. Use ONLY when the question is about collection effort or "
                  "the Data Bank's own size, never as the answer to 'how many "
                  "records are there'."),
        args=(), table="", kinds=("collection",),
        build=lambda a: ("SELECT source, count(*) AS n, count(DISTINCT author_hash) "
                         "AS authors FROM retained GROUP BY source ORDER BY n DESC", ())),
}


def describe_registry() -> str:
    """The registry as the planner sees it. Generated from the specs so a query
    added here cannot be forgotten in a prompt written somewhere else."""
    out = []
    for name, spec in QUERIES.items():
        args = ", ".join(spec.args) or "none"
        out.append(f"- `{name}` (args: {args}) — {spec.describe}")
    return "\n".join(out)


def _cite_for(table: str, row: dict) -> dict | None:
    cols = CITABLE.get(table)
    if not cols:
        return None
    try:
        return {"table": table, "key": "|".join(str(row[c]) for c in cols)}
    except KeyError:
        return None


def run_query(con: sqlite3.Connection, name: str, args: dict | None = None) -> list[dict]:
    """Run one whitelisted query. An unknown name returns nothing rather than
    raising: the planner is a model, it will occasionally invent a query name,
    and the correct consequence is that the gate sees missing evidence — not a
    stack trace in a public app."""
    spec = QUERIES.get(name)
    if spec is None:
        return []
    try:
        sql, params = spec.build(args or {})
        rows = [dict(r) for r in con.execute(sql, params)]
    except (sqlite3.Error, KeyError, TypeError, ValueError):
        return []
    for r in rows:
        r["_query"] = name
        cite = _cite_for(spec.table, r)
        if cite:
            r["_cite"] = cite
    return rows


def _default_query_for(kind: str) -> str | None:
    """The registry query that supplies a given evidence kind.

    Derived from the specs rather than written out, so a query added to the
    registry cannot fall out of sync with this. Declaration order in `QUERIES`
    decides ties, and it is ordered so the general query wins: `prevalence`
    resolves to `code_prevalence` rather than `top_codes`, `stage` to
    `stage_outcome` rather than `stage_inversion`.
    """
    for name, spec in QUERIES.items():
        if kind in spec.kinds:
            return name
    return None


def plan_codes(plan: dict) -> list[str]:
    """The codes a plan names, with bare stage letters removed.

    The planner writes "A" meaning the journey stage. Left in the code list it
    is looked up as a code, found missing, and reported as "too few records for
    A" — a fabricated shortage that downgraded a correctly-answerable question.
    Stripped in one place so retrieval and the gate cannot disagree about what
    the question is about.
    """
    return _codes({"codes": (plan.get("entities") or {}).get("codes") or []})


def fulfil_plan(plan: dict) -> list[dict]:
    """Ensure every declared evidence kind actually gets queried.

    THE BUG THIS FIXES WAS THE WORST ONE IN THE PHASE. The planner declares
    `evidence_needed` and separately picks `queries`, and the two drift: NUM-03
    ("how many records raise fit and size uncertainty?") declared it needed
    source mix and journey stage, then queried neither. The gate duly reported
    "the corpus holds nothing on where the records came from" — which is FALSE.
    The corpus has all of it.

    A gate that invents a limitation is the mirror image of a model that
    invents a finding, and it is arguably worse here, because false modesty
    reads as rigour and nobody challenges it. Fifteen of the twenty-two
    misroutes in the first full sweep were this.

    The division of labour is now the sensible one: the planner says WHAT
    evidence would settle the question, and the system knows WHICH query
    supplies it. Anything the planner asked for on top is still honoured.
    """
    queries = list(plan.get("queries") or [])
    have = {str(q.get("query")) for q in queries}
    codes = plan_codes(plan)

    for kind in dict.fromkeys(str(k).lower() for k in (plan.get("evidence_needed") or [])):
        name = _default_query_for(kind)
        if not name or name in have:
            continue
        spec = QUERIES[name]
        args: dict = {}
        if "codes" in spec.args and codes:
            args["codes"] = codes
        queries.append({"query": name, "args": args})
        have.add(name)
    return queries


def channel1(con: sqlite3.Connection, plan_queries: list[dict]) -> list[dict]:
    """Structured facts. `plan_queries` is [{"query": name, "args": {...}}]."""
    out: list[dict] = []
    seen: set[str] = set()
    for item in plan_queries or []:
        name = str((item or {}).get("query", ""))
        rows = run_query(con, name, (item or {}).get("args") or {})
        for r in rows:
            key = f"{name}:{r.get('_cite', {}).get('key', json.dumps(r, default=str)[:120])}"
            if key not in seen:
                seen.add(key)
                out.append(r)
    return out


# ---------------------------------------------------------------------------
# Channel 2 / 5 — BM25 over text
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9']+")

# Deliberately short. An aggressive stoplist strips the Hinglish function words
# that carry meaning in this corpus ("bhi", "hi", "toh"), and BM25's IDF term
# already discounts anything that appears everywhere.
_STOP = {"the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on",
         "for", "is", "are", "was", "were", "be", "been", "it", "its", "this",
         "that", "with", "as", "at", "by", "from", "i", "you", "they", "we",
         "do", "does", "did", "so", "not", "no", "my", "me", "he", "she",
         "what", "why", "how", "when", "which", "who", "there", "their"}


def tokenise(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(str(text).lower()) if t not in _STOP and len(t) > 1]


@st.cache_resource(show_spinner=False)
def _bm25_index(fingerprint: tuple, scope: str) -> dict:
    """Built once per corpus file, per scope. Keyed on the same file
    fingerprint `db.py` uses, so a replaced database yields a rebuilt index
    rather than one silently describing the previous corpus."""
    from rank_bm25 import BM25Okapi

    con = appdb.connection()
    if con is None:
        return {"ids": [], "bm25": None, "rows": {}}

    if scope == "curated":
        # NOT drawn through POOL. The relevance pass judges whether a user is
        # discussing their own save-to-purchase decision; published research
        # about cart abandonment is not that and was never scored, so joining
        # on `is_relevant = 1` silently emptied this channel. Curated items are
        # scoped by being curated, and `text_available = 1` is the real filter:
        # a paywalled or image-only item was never read and must never be
        # quoted (EC-COL-14).
        sql = ("SELECT r.* FROM records r JOIN retained t "
               "ON t.record_id = r.record_id "
               "WHERE r.source = 'curated' AND r.text_available = 1")
    else:
        sql = POOL
    rows = {r["record_id"]: dict(r) for r in con.execute(sql)}
    ids = list(rows)
    corpus = [tokenise(rows[i].get("text_clean") or rows[i].get("text_raw") or "")
              for i in ids]
    # BM25Okapi divides by average document length; an empty corpus is a
    # ZeroDivisionError, and an empty corpus is a real state before P1 has run.
    bm25 = BM25Okapi(corpus) if corpus else None
    return {"ids": ids, "bm25": bm25, "rows": rows}


def _record_ids_for_codes(con: sqlite3.Connection, codes: list[str]) -> dict[str, list[dict]]:
    """record_id -> the classification rows for the requested codes. This is
    what makes Channel 2 a filter rather than a similarity guess: the corpus is
    already labelled, so 'fit-uncertainty quotes' is an exact set."""
    if not codes:
        return {}
    where, params = _in_clause("code", codes)
    out: dict[str, list[dict]] = {}
    for r in con.execute(
            "SELECT record_id, code, confidence, evidence_span, is_blocking "
            f"FROM classifications WHERE {where}", tuple(params)):
        out.setdefault(r["record_id"], []).append(dict(r))
    return out


def _search(scope: str, terms: list[str], allowed: set[str] | None, k: int) -> list[dict]:
    idx = _bm25_index(appdb._fingerprint(), scope)
    if idx["bm25"] is None or not idx["ids"]:
        return []
    scores = idx["bm25"].get_scores(terms or ["wishlist"])
    ranked = sorted(zip(idx["ids"], scores), key=lambda x: -x[1])
    out = []
    for rid, score in ranked:
        if allowed is not None and rid not in allowed:
            continue
        if score <= 0 and len(out) >= 1:
            # Zero-scoring documents share no term with the question. Keeping
            # them would let a quote about delivery times illustrate a claim
            # about fit, which is the failure a code filter alone does not catch.
            break
        out.append({**idx["rows"][rid], "_bm25": round(float(score), 3)})
        if len(out) >= k:
            break
    return out


def _annotate(hits: list[dict], by_code: dict[str, list[dict]],
              only: str | None = None) -> list[dict]:
    for h in hits:
        cls = by_code.get(h["record_id"], [])
        h["_codes"] = [c["code"] for c in cls]
        spans = [c["evidence_span"] for c in cls
                 if c.get("evidence_span") and (only is None or c["code"] == only)]
        h["_span"] = spans[0] if spans else next(
            (c["evidence_span"] for c in cls if c.get("evidence_span")), None)
        h["_confidence"] = max((c["confidence"] or 0) for c in cls) if cls else None
        h["_cite"] = {"table": "record", "key": h["record_id"]}
    return hits


def channel2(con: sqlite3.Connection, codes: list[str], terms: list[str],
             k: int = 6) -> list[dict]:
    """Verbatim evidence for the codes in the plan, ranked by the question's own
    words. Returns the record plus the classifier's `evidence_span` — the exact
    substring that caused the label, already verified against `text_raw` at
    write time (S2-INV-2), so a quote lifted from it is anchored twice.

    WHY IT RETRIEVES PER CODE WHEN SEVERAL ARE NAMED
    ------------------------------------------------
    Pooling twenty codes into one BM25 pass makes the code filter meaningless —
    the allowed set becomes most of the corpus, and what comes back is whatever
    happens to share words with the question. The first live run returned, for
    "what stops people buying?", a quote about counting posts and comments. So
    when a question names several codes the retrieval is done per code and the
    results interleaved: each quote then illustrates a specific barrier, which
    is what "In users' words" is for.
    """
    by_code = _record_ids_for_codes(con, codes)
    if not codes:
        return _annotate(_search("all", terms, None, k), by_code)

    if len(codes) == 1:
        return _annotate(_search("all", terms, set(by_code), k), by_code, codes[0])

    # Order the codes by prevalence so the quotes lead with the barriers the
    # answer is actually about, not with whichever id sorts first.
    where, params = _in_clause("code", codes)
    ranked = [r["code"] for r in con.execute(
        f"SELECT code FROM analysis_code_prevalence WHERE {where} ORDER BY n DESC",
        tuple(params))] or codes

    per = max(1, k // min(len(ranked), 4))
    out, seen = [], set()
    for code in ranked[:4]:
        allowed = {rid for rid, cls in by_code.items()
                   if any(c["code"] == code for c in cls)} - seen
        for h in _annotate(_search("all", terms, allowed, per), by_code, code):
            seen.add(h["record_id"])
            out.append(h)
        if len(out) >= k:
            break
    return out[:k]


def channel5(con: sqlite3.Connection, terms: list[str], k: int = 3) -> list[dict]:
    """External corroboration — or contradiction. The curated sub-corpus is
    published research, URL-verified at collection time. Items marked
    `text_available = 0` were paywalled or image-only and are excluded from the
    index entirely: never quote what was not read (EC-COL-14)."""
    hits = _search("curated", terms, None, k)
    for h in hits:
        h["_cite"] = {"table": "record", "key": h["record_id"]}
    return hits


# ---------------------------------------------------------------------------
# Channel 3 — disconfirming evidence
# ---------------------------------------------------------------------------

def channel3(con: sqlite3.Connection, codes: list[str], stages: list[str],
             terms: list[str]) -> dict[str, list[dict]]:
    """Retrieves AGAINST the emerging answer, in three directions.

    This channel is why the system investigates rather than confirms. It runs
    on every answer that names a code, whether or not the planner asked for it,
    because a planner that has decided what the answer is will not think to ask
    for the evidence that spoils it.
    """
    codes = [c.upper() for c in codes or []]
    out: dict[str, list[dict]] = {"rivals": [], "complications": [], "residual": []}
    if not codes and not stages:
        return out

    # 1. Rival codes — the other barriers in the same stage(s), which are what a
    #    reader comparing against this claim would reach for.
    stage_set = {s.upper()[:1] for s in (stages or [])}
    stage_set |= {c[0] for c in codes if c and c[0].isalpha()}
    if stage_set:
        where, params = _in_clause("stage", sorted(stage_set))
        ex, exp = _in_clause("code", codes)
        sql = (f"SELECT * FROM analysis_code_prevalence WHERE {where} "
               + (f"AND code NOT IN ({','.join('?' * len(codes))}) " if codes else "")
               + f"AND n >= {MIN_N_VISIBLE} ORDER BY n DESC LIMIT 5")
        rows = [dict(r) for r in con.execute(sql, tuple(params) + tuple(codes))]
        for r in rows:
            r["_cite"] = _cite_for("analysis_code_prevalence", r)
            r["_query"] = "rival_codes"
        out["rivals"] = rows

    # 2. Complicating co-occurrences — what else is in the record when this
    #    barrier is raised. A barrier that never appears alone is not the
    #    single cause an answer might otherwise imply.
    if codes:
        ph = ",".join("?" * len(codes))
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM analysis_cooccurrence WHERE min_support_met = 1 "
            f"AND (code_a IN ({ph}) OR code_b IN ({ph})) "
            "ORDER BY lift DESC LIMIT 6", tuple(codes) * 2)]
        for r in rows:
            r["_cite"] = _cite_for("analysis_cooccurrence", r)
            r["_query"] = "complicating_cooccurrence"
        out["complications"] = rows

    # 3. The residual — records the codebook could not classify that nonetheless
    #    match the question's words. If the answer to a question is sitting in
    #    Z-99, no amount of code-filtered retrieval will ever find it.
    z_ids = {r["record_id"] for r in con.execute(
        "SELECT DISTINCT record_id FROM classifications WHERE code LIKE 'Z%'")}
    if z_ids:
        for h in _search("all", terms, z_ids, 3):
            h["_cite"] = {"table": "record", "key": h["record_id"]}
            h["_codes"] = ["Z-99"]
            h["_span"] = None
            out["residual"].append(h)
    return out


# ---------------------------------------------------------------------------
# Channel 4 — method and limitations
# ---------------------------------------------------------------------------

def channel4(con: sqlite3.Connection, codes: list[str], stages: list[str],
             sources: list[str] | None = None) -> dict[str, list[dict]]:
    """What must be said about the evidence, retrieved rather than remembered.

    The flags are matched to what is actually in play. A binding `*` flag fires
    on every answer; a Stage A question additionally gets the under-detection
    flag; a C10 question gets the kappa-0.10 warning whether or not the model
    would have thought of it. That targeting is the whole point — a fixed
    boilerplate caveat is ignored by readers precisely because it is fixed.
    """
    codes = [c.upper() for c in codes or []]
    targets = {"*"} | set(codes) | {s.upper()[:1] for s in (stages or [])} \
        | {c[0] for c in codes if c and c[0].isalpha()} | set(sources or [])

    flags = []
    for r in con.execute("SELECT * FROM analysis_method_flags"):
        d = dict(r)
        applies = set(json.loads(d["applies_to"]))
        if applies & targets:
            d["_cite"] = _cite_for("analysis_method_flags", d)
            flags.append(d)
    # binding first — an answer that truncates should truncate the optional half.
    order = {"binding": 0, "important": 1, "context": 2}
    flags.sort(key=lambda d: (order.get(d["severity"], 3), d["flag_id"]))

    agreement, mix = [], []
    if codes:
        where, params = _in_clause("code", codes)
        for r in con.execute(f"SELECT * FROM analysis_gold_agreement WHERE {where}",
                             tuple(params)):
            d = dict(r)
            d["_cite"] = _cite_for("analysis_gold_agreement", d)
            agreement.append(d)
        for r in con.execute(f"SELECT * FROM analysis_source_code WHERE {where} "
                             "ORDER BY code, n DESC", tuple(params)):
            d = dict(r)
            d["_cite"] = _cite_for("analysis_source_code", d)
            mix.append(d)
    return {"flags": flags, "agreement": agreement, "source_mix": mix}


# ---------------------------------------------------------------------------
# Step 3 — the gate
# ---------------------------------------------------------------------------

@dataclass
class Retrieved:
    """Everything the channels returned, in one object so the gate and the
    verifier read the same thing the synthesis call was given."""
    facts: list[dict] = field(default_factory=list)          # channel 1
    verbatims: list[dict] = field(default_factory=list)      # channel 2
    counter: dict = field(default_factory=dict)              # channel 3
    method: dict = field(default_factory=dict)               # channel 4
    external: list[dict] = field(default_factory=list)       # channel 5

    def analysis_rows(self) -> list[dict]:
        """Every citable analysis row retrieved, from any channel. This is the
        set S4-INV-2 checks the answer's numbers against."""
        rows = list(self.facts)
        rows += self.counter.get("rivals", []) + self.counter.get("complications", [])
        rows += self.method.get("flags", []) + self.method.get("agreement", []) \
            + self.method.get("source_mix", [])
        return rows

    def records(self) -> list[dict]:
        """Every record retrieved, from any channel. The set a quote must come
        from."""
        return (list(self.verbatims) + list(self.counter.get("residual", []))
                + list(self.external))


# What the planner may ask for. A CLOSED set is what makes the gate
# deterministic: free-text evidence needs ("prevalence+n for both") cannot be
# mechanically compared against what came back, so the verdict would collapse
# into the model's own opinion of whether it had enough — the exact judgement
# the gate exists to take away from it.
REQUIREMENT_KINDS = (
    "prevalence", "ranking", "verbatim", "source_breakdown", "segment_split",
    "cooccurrence", "counterfactual", "intensity", "outcome", "stage",
    "opportunity", "robustness", "hypothesis", "insight", "cluster", "novelty",
    "subcode", "addressable", "recommendation", "composition", "confidence",
    "reliability", "bias", "method", "external", "counter_evidence",
)


# What each requirement is, said in a reader's words. The gate's reasons are
# handed to the synthesis call AND shown in the app, so a reason written as
# "no subcode rows retrieved" reaches a PM as engine jargon — which is how the
# first live PARTIAL answer opened. The gap has to be nameable in the answer,
# and it cannot be named in words the reader does not have.
KIND_PHRASE = {
    "prevalence": "how often this is raised",
    "ranking": "an ordering of these barriers",
    "verbatim": "what people actually said about this",
    "source_breakdown": "whether this holds up across sources",
    "segment_split": "how this differs between kinds of shopper",
    "cooccurrence": "what else comes up alongside this",
    "counterfactual": "whether people said they would have bought otherwise",
    "intensity": "how much effort people spend working around this",
    "outcome": "whether people abandon or merely postpone",
    "stage": "where in the journey this happens",
    "opportunity": "how this ranks as an opportunity",
    "robustness": "whether the ranking survives different priorities",
    "hypothesis": "a testable hypothesis about this",
    "insight": "a written-up finding on this",
    "cluster": "what the blind clustering found here",
    "novelty": "whether anything here was unanticipated",
    "subcode": "a finer breakdown of what this is about",
    "addressable": "how much of the opportunity this represents",
    "recommendation": "which group to target",
    "composition": "where the records came from",
    "confidence": "how well-supported this is",
    "reliability": "how reliably this was classified",
    "bias": "the known blind spots here",
    "method": "how this was measured",
    "external": "published research bearing on this",
    "counter_evidence": "evidence against this",
}


def _phrase(kind: str) -> str:
    return KIND_PHRASE.get(kind, kind.replace("_", " "))


def _rows_for_kind(kind: str, got: Retrieved) -> list[dict]:
    kinds_by_query = {n: s.kinds for n, s in QUERIES.items()}
    return [r for r in got.facts
            if kind in kinds_by_query.get(str(r.get("_query", "")), ())]


def _satisfied(kind: str, codes: list[str], got: Retrieved) -> tuple[bool, str]:
    """Is one evidence requirement met? Returns (met, why-not).

    The minimum-n floor is applied HERE, identically to the way charts apply it
    (EC-CHAT-5). A question about a barrier with 8 records must not be answered
    as though it had 800, and the failure has to be structural: a model told
    "be careful with small numbers" will still rank them.
    """
    if kind == "method":
        return (bool(got.method.get("flags")), "the method notes could not be loaded")

    if kind == "verbatim":
        n = len(got.verbatims)
        return (n >= 2, f"too few records to quote — only {n} matched this question")

    if kind == "counter_evidence":
        c = got.counter
        n = len(c.get("rivals", [])) + len(c.get("complications", [])) + len(c.get("residual", []))
        return (n >= 1, "nothing was found that argues against this")

    if kind == "external":
        return (bool(got.external), "no published research in the collection bears on this")

    rows = _rows_for_kind(kind, got)
    if not rows:
        return (False, f"the corpus holds nothing on {_phrase(kind)}")

    # A count-bearing row below the visibility floor is not evidence. Below the
    # ranking floor it is evidence, but not evidence for an ORDERING — so a
    # ranking requirement is held to the higher bar.
    floor = MIN_N_RANKED if kind == "ranking" else MIN_N_VISIBLE
    counted = [r for r in rows if isinstance(r.get("n"), (int, float))]
    if counted:
        ok = [r for r in counted if (r.get("n") or 0) >= floor]
        if not ok:
            best = max((r.get("n") or 0) for r in counted)
            return (False, f"too few records for {_phrase(kind)} — the largest count "
                           f"is {best:g}, under the {floor} needed"
                           f"{' to put them in order' if kind == 'ranking' else ' to report it'}")
        # Per-code only where the rows actually carry a code. Stage, outcome and
        # addressable rows are keyed on something else entirely, and asking them
        # "is C1 above the floor?" got the answer "no" for every code — turning
        # correctly retrieved evidence into a fabricated gap.
        keyed = [r for r in counted if r.get("code")]
        if codes and keyed:
            thin = [c for c in codes
                    if not any(str(r.get("code", "")).upper() == c and
                               (r.get("n") or 0) >= floor for r in keyed)]
            # Failing the whole requirement because SOME named code is thin is
            # wrong, and it was wrong in the direction that matters: a broad
            # question naming twenty codes would be downgraded to PARTIAL
            # because the twentieth has four records, while the evidence for the
            # question actually asked was complete. A requirement is unmet only
            # when NOTHING it names clears the floor. The thin ones are carried
            # forward as a caveat instead — reported, not silently dropped.
            # The FIRST code the planner names is the question's subject; the
            # rest are comparison anchors and context. That distinction is what
            # separates "how big is cost surprise?" (subject D1, n=14 — must
            # not answer as though supported) from "what stops people buying?"
            # (subject C2, n=241, with one thin code named in passing).
            #
            # Failing on ANY thin code manufactured gaps on broad questions;
            # failing on NONE let a genuine low-n question answer as FULL,
            # which defeats the minimum-n floor entirely. Both were observed in
            # the first sweep, in opposite directions.
            subject = codes[0] if codes else None
            if subject and subject in thin:
                return (False, f"too few records for {_phrase(kind)} — {subject} is "
                               f"under the {floor} needed"
                               f"{' to put them in order' if kind == 'ranking' else ''}")
            if thin and len(thin) == len(codes):
                return (False, f"too few records for {_phrase(kind)} — under the {floor} "
                               f"needed, for {', '.join(thin)}")
            if thin:
                return (True, f"~{_phrase(kind)}: too thin to report for "
                              f"{', '.join(thin)}")
    return (True, "")


@dataclass
class Verdict:
    route: str                      # FULL | PARTIAL | NONE
    met: list[str] = field(default_factory=list)
    unmet: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # Requirements that were met, but not for every code named. Not a gap in
    # the answer — a limit on how far it can be taken — so it is carried to the
    # brief rather than routing the question to PARTIAL.
    caveats: list[str] = field(default_factory=list)

    @property
    def gap(self) -> str:
        """The sentence a PARTIAL answer must contain. Written here rather than
        by the model, because 'name the gap' (S4-HUM-2) is a promise the model
        will otherwise keep by gesturing at it."""
        return "; ".join(self.reasons)


# Cuts this corpus does not have, and the plain words a question uses to ask for
# one. EC-CHAT-13 — "the data exists at a different cut" — is the single most
# common PARTIAL, and leaving its detection to the planner made the ROUTE
# NON-DETERMINISTIC: "do users trust influencer reviews?" came back PARTIAL on
# one run and FULL on the next, because the first plan happened to request a
# sub-theme breakdown and the second did not. The behaviour was right both
# times — both answers named the gap — but a route that moves cannot be
# asserted, and architecture.md §8.5 rests on it not moving.
#
# So the absent dimensions are registered here, matched against the question
# itself, and applied AFTER the plan. What the corpus lacks is a fact about the
# corpus; it should not depend on what a model thought to ask for.
MISSING_CUTS: list[tuple[str, str]] = [
    (r"\binfluencer|celebrit|creator\b",
     "the corpus does not separate influencer content from ordinary buyer reviews"),
    (r"\bbrand(s|ed)?\b|\bmyntra vs|\bajio\b|\bnykaa\b",
     "barriers are not classified by brand, so no brand-level comparison exists"),
    (r"\bbangalore|bengaluru|mumbai|delhi|chennai|hyderabad|pune|kolkata|"
     r"\bcity\b|\bregion|\btier[- ]?[123]\b|\bmetro\b",
     "no geographic data was collected, so no location breakdown exists"),
    (r"\bmen\b|\bwomen\b|\bmale\b|\bfemale\b|\bgender|\bage\b|\bage group|"
     r"\byoung(er)?\b|\bolder\b|\bdemographic",
     "no demographic data was collected, so no split by gender or age exists"),
    (r"\bover time\b|\btrend|\blast (two |2 )?years?\b|\bgot worse\b|\bgetting worse\b|"
     r"\bmonth[- ]on[- ]month|\byear[- ]on[- ]year|\bsince \d{4}",
     "the corpus was collected in a single window, so it cannot show a trend"),
    (r"\brevenue|\bsales\b|\bgmv\b|\bprofit|\bcrore|\bhow much money|\bworth ₹",
     "the corpus holds no financial or transaction data"),
    (r"\bgift(s|ing)?\b",
     "whether a save was intended as a gift is not a coded dimension"),
    (r"\bcome back\b|\breturn(ed)? later\b|\bsame user\b|\bindividual user|"
     r"\bcohort|\bretention",
     "records are not linked to individuals over time, so no one can be followed"),
]


def missing_cuts(question: str) -> list[str]:
    q = str(question or "").lower()
    return [why for pattern, why in MISSING_CUTS if re.search(pattern, q)]


# Questions ASKING FOR A METRIC this corpus structurally cannot produce. These
# refuse deterministically, whatever the plan says.
#
# Relaxing the out-of-scope rule — so that a planner's doubt could be overruled
# by the evidence — resurrected the single most important refusal in the whole
# set: "what is Myntra's conversion rate from wishlist to purchase?" came back
# PARTIAL. That is the project's central methodological claim breaking in
# public, and it must not depend on a model's label.
#
# The pattern targets the REQUEST FOR THE VALUE, not the vocabulary. "What is
# the conversion rate?" is unanswerable; "your data shows 40% drop off — what
# causes that?" is a false premise about checkout barriers the corpus does
# cover, and it must still be answered with the premise corrected.
HARD_OUT_OF_SCOPE = re.compile(
    r"\b(what(?:'s| is| are)?|which|who|how (?:much|many|big|large)|give me|"
    r"tell me|show me|calculate|estimate)\b[^?.]{0,60}?\b("
    r"conversion rate|drop[- ]?off rate|abandonment rate|retention rate|churn rate|"
    r"return rate|click[- ]?through|revenue|turnover|gmv|profit|valuation|market share|"
    r"daily active|monthly active|active users|share price|net promoter)\b", re.I)

# Questions about the CURRENT state of the platform. The corpus holds people's
# EXPERIENCE of returns and delivery, which is a different thing from the policy
# in force today — answering one with the other states an out-of-date operational
# fact as current, and it is the kind of wrong answer that looks well-sourced.
CURRENT_STATE = re.compile(
    r"\b(what|which|how)\b[^?.]{0,50}\b(policy|policies|charge|fee|price list|"
    r"terms|rules?)\b[^?.]{0,40}\b(right now|currently|today|at the moment|now)\b"
    r"|\bcurrent\s+(return|refund|delivery|shipping|exchange)\s+(policy|terms|rules?)\b",
    re.I)


def hard_out_of_scope(question: str) -> bool:
    q = str(question or "")
    return bool(HARD_OUT_OF_SCOPE.search(q) or CURRENT_STATE.search(q))


def gate(plan: dict, got: Retrieved, question: str = "") -> Verdict:
    """FULL / PARTIAL / NONE, decided by comparing the plan against what came
    back. No model involvement, so the same question always routes the same way
    and `evals.md` can assert it (AC-4)."""
    intent = str(plan.get("intent", "")).lower()
    disowned = intent == "out_of_scope" or str(plan.get("answerable", "")).lower() == "no"

    if hard_out_of_scope(question):
        return Verdict("NONE", [], list(plan.get("evidence_needed") or []),
                       ["this corpus measures what people say, not what they do — "
                        "it holds no funnel, transaction or company data, so a rate "
                        "of this kind cannot be produced from it at all"])

    # A plan that calls a question out of scope AND requests seven queries
    # against the corpus is contradicting itself. Five of the twenty-two
    # misroutes in the first sweep were this: "what do Bangalore shoppers think
    # about wishlist pricing?" was labelled out_of_scope while the same plan
    # asked for prevalence, source mix and counterfactuals — and the label won,
    # discarding a well-evidenced half-answer.
    #
    # The label loses when the evidence contradicts it, for the same reason the
    # absent cuts are registered as data: a model's opinion about what the
    # corpus holds should not override what the corpus actually returns. It
    # never wins outright either — a question the planner doubted is capped at
    # PARTIAL, never FULL, because that doubt is itself a signal.
    if disowned and not (plan.get("queries") or []):
        return Verdict("NONE", [], list(plan.get("evidence_needed") or []),
                       ["the question falls outside what this corpus covers"])
    if disowned and not got.facts:
        return Verdict("NONE", [], list(plan.get("evidence_needed") or []),
                       ["the question falls outside what this corpus covers"])
    # NO RULE HERE COMBINING "the planner disowned it" WITH "a cut is missing".
    # That was tried, to catch "which brand has the highest return rate?", and it
    # refused four questions that are the whole point of the PARTIAL route:
    # "what do Bangalore shoppers think about pricing?" has no geography AND was
    # disowned, and the answer is still most of an answer. A missing cut is a
    # reason to name a gap, not to withhold what the corpus does hold. The
    # brand-rate case belongs to `hard_out_of_scope`, which catches it by asking
    # what the question wants — a rate — rather than by counting doubts.
    # EC-CHAT-6 routes method questions away from corpus counts, NOT away from
    # evidence. They are answered from the registered method flags and the
    # agreement rows — which are citable — and are held to the same checks as
    # everything else. Short-circuiting to FULL here meant "how did you validate
    # this?" returned an unverified answer.
    if intent == "methodological" and not (plan.get("evidence_needed") or []):
        return Verdict("FULL", ["method"], [], [])

    needs = [str(k).lower() for k in (plan.get("evidence_needed") or [])
             if str(k).lower() in REQUIREMENT_KINDS]
    if not needs:
        needs = ["prevalence"]
    codes = plan_codes(plan)

    # Applied to the question AND the restatement: the user may name the absent
    # cut in words the planner then paraphrases away.
    absent = missing_cuts(f"{question} {plan.get('restated', '')}")

    met, unmet, reasons, caveats = [], [], [], []
    for kind in dict.fromkeys(needs):
        ok, why = _satisfied(kind, codes, got)
        if ok:
            met.append(kind)
            if why.startswith("~"):
                caveats.append(why[1:])
        else:
            unmet.append(kind)
            reasons.append(why)

    if absent:
        unmet = unmet + ["missing_cut"]
        reasons = reasons + absent

    if not met:
        return Verdict("NONE", met, unmet,
                       reasons or ["nothing relevant was retrieved"], caveats)
    if unmet or disowned:
        if disowned and not reasons:
            reasons = ["parts of this question reach past what the corpus covers"]
        return Verdict("PARTIAL", met, unmet, reasons, caveats)
    return Verdict("FULL", met, unmet, [], caveats)


# ---------------------------------------------------------------------------
# Orchestration of steps 2 and 3
# ---------------------------------------------------------------------------

def retrieve(con: sqlite3.Connection, plan: dict) -> Retrieved:
    """Run the channels the plan calls for — plus the two that always run.

    Channels 3 and 4 are NOT optional and are not the planner's choice. A plan
    that has decided the answer will not request the evidence against it, and a
    plan focused on a number will not request the caveat that qualifies it.
    Making them unconditional is how "a researcher looks for disconfirming
    evidence" becomes a property of the system instead of a habit of the prompt.
    """
    ent = plan.get("entities") or {}
    codes = [str(c).upper() for c in (ent.get("codes") or [])]
    stages = [str(s) for s in (ent.get("stages") or [])]
    sources = [str(s) for s in (ent.get("sources") or [])]
    terms = tokenise(" ".join(filter(None, [
        str(plan.get("restated", "")),
        " ".join(str(q) for q in (plan.get("sub_questions") or [])),
    ])))

    got = Retrieved()
    got.facts = channel1(con, fulfil_plan(plan))
    needs = {str(k).lower() for k in (plan.get("evidence_needed") or [])}
    # ALWAYS, for the same reason channels 3 and 4 always run. "How many records
    # are in the corpus?" names no code and does not ask for verbatim, so this
    # was skipped and the answer had literally nothing to quote — while the
    # contract requires every FULL answer to show one human sentence behind the
    # number. Retrieval must supply what the contract demands, or the contract
    # is asking the model to invent it.
    got.verbatims = channel2(con, codes, terms)
    got.counter = channel3(con, codes, stages, terms)          # always
    got.method = channel4(con, codes, stages, sources)         # always
    if "external" in needs:
        got.external = channel5(con, terms)
    return got
