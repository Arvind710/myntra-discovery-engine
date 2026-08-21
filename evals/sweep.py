"""Run the golden question set once, and write the result the P4 gate is taken
against.

WHY THE SWEEP IS SEPARATE FROM THE TESTS
----------------------------------------
Sixty-four questions is two LLM calls each and a few dollars. Running that
inside pytest would mean paying for it on every test invocation, and would make
the gate un-rerunnable — you could never check a fix without re-buying the whole
sweep. So the sweep is a run, it writes an artefact under a `run_id`, and
`test_phase4_chatbot.py` asserts against that artefact. Exactly the way every
other gate in this project is taken: against a named run, not against whatever
the code happens to do at the moment the test executes.

The per-question record is deliberately fat — plan, route, gate reasons, the
full answer, every verifier finding, cost and latency. A gate report that says
"T-9 87%" and cannot show which six questions routed wrongly is not a gate
report, and the answer text is what S4-HUM-1 and S4-HUM-2 are read from.

Usage:
    python evals/sweep.py                     # the whole set
    python evals/sweep.py --category partial  # one category, while iterating
    python evals/sweep.py --limit 5 --dry-run # plan and retrieve only, no synthesis
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from pipeline.common import db as dbm            # noqa: E402
from pipeline.common import env as envm          # noqa: E402
from pipeline.common import runs as rmod         # noqa: E402

FIXTURES = ROOT / "evals" / "fixtures"
REPORTS = ROOT / "evals" / "reports"


def load_questions() -> list[dict]:
    return yaml.safe_load((FIXTURES / "golden_questions.yaml").read_text())["questions"]


def load_payloads() -> dict[str, dict]:
    """The injection fixture, keyed by attack name.

    These records are NOT in the corpus and must never be — they are seeded
    into the retrieval result at ask time so the payload arrives THROUGH
    RETRIEVAL, which is how a real one would. Pasting a payload into the
    question box tests the input, and the input is not the attack surface here:
    the corpus is.
    """
    out = {}
    for line in (FIXTURES / "injection_records.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["attack"]] = r
    return out


def expected_routes(spec) -> list[str]:
    """`FULL` or `any-of [FULL, PARTIAL]` -> the list of acceptable routes."""
    s = str(spec).strip()
    if s.lower().startswith("any-of"):
        return [x.strip().upper() for x in s[s.find("[") + 1:s.rfind("]")].split(",")]
    return [s.upper()]


def out_partial(run_id: str, results: list[dict], A) -> dict:
    return {
        "run_id": run_id,
        "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "planner_model": A.PLANNER_MODEL, "synthesis_model": A.SYNTHESIS_MODEL,
        "synthesis_effort": A.SYNTHESIS_EFFORT,
        "prompt_version": A.PROMPT_VERSION,
        "n": len(results),
        "cost_usd": round(sum(r.get("cost_usd", 0) for r in results), 4),
        "results": results,
    }


def _write(out: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"p4_sweep_{out['run_id']}.json"
    payload = json.dumps(out, indent=2, ensure_ascii=False)
    path.write_text(payload)
    (REPORTS / "p4_sweep_latest.json").write_text(payload)
    return path


def run(questions: list[dict], *, dry_run: bool = False,
        budget: float | None = None, resume: str | None = None,
        redo: set[str] | None = None) -> dict:
    envm.load()
    from openai import OpenAI
    from lib import db as appdb
    from lib import analyst as A
    from lib import retrieval as R

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=300.0)
    con = appdb.connection()
    payloads = load_payloads()
    write_con = dbm.connect()

    # WHY THIS WRITES AFTER EVERY QUESTION.
    # The artefact used to be written once, at the end. When the credit balance
    # ran out on question 30 of 64, twenty-nine completed answers — real money,
    # already spent — went with it. A long paid run must never hold its only
    # copy in memory.
    results: list[dict] = []
    done: dict[str, dict] = {}
    if resume:
        prev = REPORTS / f"p4_sweep_{resume}.json"
        if prev.exists():
            for r in json.loads(prev.read_text())["results"]:
                if not r.get("error") and r["id"] not in (redo or set()):
                    done[r["id"]] = r
            print(f"resuming: {len(done)} answers carried forward from {resume}")

    spent = 0.0
    with rmod.Run(write_con, "p4-sweep", model=A.SYNTHESIS_MODEL,
                  prompt_version=A.PROMPT_VERSION,
                  params={"n": len(questions), "planner": A.PLANNER_MODEL}) as run_row:
        run_id = run_row.run_id
        for i, q in enumerate(questions, 1):
            t0 = time.time()
            if q["id"] in done:
                results.append(done[q["id"]])
                print(f"[{i}/{len(questions)}] {q['id']:8} carried forward", flush=True)
                continue
            if budget is not None and spent >= budget:
                print(f"\nSTOPPING at {i - 1}/{len(questions)} — ${spent:.2f} spent "
                      f"reaches the ${budget:.2f} budget. Everything answered so far "
                      f"is saved; re-run with --resume to finish.", flush=True)
                break
            # Follow-up questions carry their prior turn. The restatement is
            # what the planner resolves against, and for the fixture we use the
            # prior question as its own restatement — good enough to prove the
            # reference resolves, and it keeps the sweep to one call per turn.
            history = [{"question": c, "restated": c} for c in (q.get("context") or [])]
            inject = None
            if q.get("payload"):
                p = payloads.get(q["payload"])
                inject = [p] if p else None

            if dry_run:
                plan = {"intent": "exploratory", "restated": q["question"],
                        "entities": {"codes": []}, "evidence_needed": ["prevalence"],
                        "queries": [{"query": "top_codes", "args": {}}]}
                got = R.retrieve(con, plan)
                v = R.gate(plan, got, q["question"])
                results.append({"id": q["id"], "category": q["category"],
                                "route": v.route, "dry_run": True})
                print(f"[{i}/{len(questions)}] {q['id']:8} {v.route}", flush=True)
                continue

            a = A.ask(client, con, q["question"], history=history,
                      inject_records=inject)
            run_row.add_usage(
                input_tokens=sum(int(getattr(u, "input_tokens", 0) or 0)
                                 for _, _, u in a.usage),
                output_tokens=sum(int(getattr(u, "output_tokens", 0) or 0)
                                  for _, _, u in a.usage))
            run_row.n_output += 1

            rep = a.report
            results.append({
                "id": q["id"], "category": q["category"], "question": q["question"],
                "expect_route": q["expect_route"],
                "expected": expected_routes(q["expect_route"]),
                "assertions": q.get("assertions") or {},
                "payload": q.get("payload"),
                "route": a.route, "restated": a.restated, "answer": a.text,
                "error": a.error,
                "plan": {"intent": a.plan.get("intent"),
                         "codes": (a.plan.get("entities") or {}).get("codes"),
                         "evidence_needed": a.plan.get("evidence_needed"),
                         "queries": [x.get("query") for x in a.plan.get("queries") or []],
                         "premise": a.plan.get("premise")},
                "gate_reasons": a.verdict.reasons if a.verdict else [],
                "gate_caveats": a.verdict.caveats if a.verdict else [],
                "verified": bool(rep.ok) if rep else False,
                "regenerated": a.regenerated,
                "problems": rep.problems() if rep else ["no report"],
                "bad_numerals": rep.bad_numerals if rep else [],
                "bad_quotes": rep.bad_quotes if rep else [],
                "proxy_violations": rep.proxy_violations if rep else [],
                "scope_violations": rep.scope_violations if rep else [],
                "n_facts": len(a.retrieved.facts) if a.retrieved else 0,
                "n_records": len(a.records),
                "record_ids": [r.get("record_id") for r in a.records],
                "cost_usd": round(a.cost_usd, 6),
                "seconds": round(time.time() - t0, 1),
            })
            spent += a.cost_usd
            _write(out_partial(run_id, results, A))     # crash-safe, every question
            ok = "ok " if a.route in expected_routes(q["expect_route"]) else "ROUTE"
            vf = "" if (rep and rep.ok) else f"  [{len(rep.problems()) if rep else '?'} problems]"
            print(f"[{i}/{len(questions)}] {q['id']:8} {ok} {a.route:8} "
                  f"${a.cost_usd:.4f} {time.time() - t0:.0f}s{vf}", flush=True)
            if a.error:
                print(f"           ERROR: {a.error}", flush=True)
                if "insufficient_quota" in a.error or "credit" in a.error.lower():
                    print("\nSTOPPING — the API reports no credit remaining. "
                          "Everything answered so far is saved; add credit and "
                          "re-run with --resume.", flush=True)
                    break

    out = out_partial(run_id, results, A)
    path = _write(out)
    print(f"\nwrote {path.relative_to(ROOT)}  —  ${out['cost_usd']:.4f} over {out['n']} questions")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--category", help="run one category only")
    ap.add_argument("--id", nargs="*", help="run specific question ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true",
                    help="plan and retrieve only — no synthesis call, no cost")
    ap.add_argument("--budget", type=float, default=None,
                    help="stop cleanly before spending more than this, in USD")
    ap.add_argument("--resume", metavar="RUN_ID",
                    help="carry forward the answers already in a previous run's "
                         "artefact and only ask what is missing")
    ap.add_argument("--redo", nargs="*", default=None, metavar="ID",
                    help="with --resume: re-ask these ids even though the "
                         "previous run answered them")
    a = ap.parse_args()

    qs = load_questions()
    if a.category:
        qs = [q for q in qs if q["category"] == a.category]
    if a.id:
        qs = [q for q in qs if q["id"] in set(a.id)]
    if a.limit:
        qs = qs[:a.limit]
    if not qs:
        print("no questions matched")
        return 1
    run(qs, dry_run=a.dry_run, budget=a.budget, resume=a.resume,
        redo=set(a.redo or []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
