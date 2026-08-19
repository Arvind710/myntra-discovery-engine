"""Emit evals/reports/<name>.md from a pytest run.

The report RENDERS INSIDE THE APP, as a Validation tab under Analysis
(evals.md §4, pinned in DECISIONS.md). This is deliberate: a mentor asking
"how do you know your classifier is right?" gets a URL, not a claim -- and
it satisfies NFR-4 auditability without extra work.

Usage:
    python evals/report.py phase0            # run the gate and write a report
    python evals/report.py phase0 --run-id <run_id>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = Path(__file__).parent / "reports"

GATE_TITLES = {
    "phase0": "P0 — Foundation & Freeze",
    "phase1": "P1 — Collection & Data Bank",
    "phase2": "P2 — Analysis",
    "phase3": "P3 — Insights & Hypotheses",
    "phase4": "P4 — Research Analyst",
    "phase5": "P5 — Release & Handoff",
}


def run_gate(marker: str) -> dict:
    out = ROOT / ".pytest_report.json"
    cmd = [sys.executable, "-m", "pytest", "evals/", "-m", marker, "-q",
           "--tb=no", f"--junit-xml={ROOT / '.pytest_junit.xml'}"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out.unlink(missing_ok=True)
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def parse_junit(path: Path) -> list[dict]:
    import xml.etree.ElementTree as ET

    if not path.exists():
        return []
    root = ET.parse(path).getroot()
    cases = []
    for tc in root.iter("testcase"):
        failure = tc.find("failure") is not None or tc.find("error") is not None
        skipped = tc.find("skipped") is not None
        cases.append({
            "name": tc.get("name", ""),
            "classname": tc.get("classname", ""),
            "time": float(tc.get("time", 0) or 0),
            "status": "SKIP" if skipped else ("FAIL" if failure else "PASS"),
            "message": (tc.find("failure").get("message", "") if tc.find("failure") is not None else ""),
        })
    return cases


def write(marker: str, cases: list[dict], rc: int, run_id: str | None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc)
    n_pass = sum(c["status"] == "PASS" for c in cases)
    n_fail = sum(c["status"] == "FAIL" for c in cases)
    n_skip = sum(c["status"] == "SKIP" for c in cases)

    verdict = "**GATE PASSED**" if rc == 0 and n_fail == 0 else "**GATE FAILED**"

    lines = [
        f"# Eval report — {GATE_TITLES.get(marker, marker)}",
        "",
        f"**Generated:** {stamp.isoformat(timespec='seconds')}",
        f"**Run id:** `{run_id or 'n/a'}`",
        f"**Result:** {verdict} — {n_pass} passed, {n_fail} failed, {n_skip} skipped",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for c in sorted(cases, key=lambda x: (x["status"] != "FAIL", x["name"])):
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}[c["status"]]
        detail = c["message"].replace("|", "\\|").splitlines()[0][:160] if c["message"] else ""
        lines.append(f"| `{c['name']}` | {icon} {c['status']} | {detail} |")

    if n_skip:
        lines += ["", f"> {n_skip} check(s) skipped — these run once the "
                      "corpus for this phase exists. A skipped check is not a passed check."]

    lines += ["", "---", "",
              "Gate discipline: invariants hard-stop; metric shortfalls enter a capped "
              "remediation loop and are then reported as stated limitations; T-6, T-10 and "
              "T-11 are absolute and have no limitation clause "
              "(`implementationplan.md` §0.3)."]

    path = REPORTS / f"gate_{marker}_{stamp:%Y%m%d}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("marker", choices=sorted(GATE_TITLES))
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    res = run_gate(args.marker)
    cases = parse_junit(ROOT / ".pytest_junit.xml")
    path = write(args.marker, cases, res["returncode"], args.run_id)
    (ROOT / ".pytest_junit.xml").unlink(missing_ok=True)

    print(res["stdout"].strip().splitlines()[-1] if res["stdout"].strip() else "")
    print(f"report: {path.relative_to(ROOT)}")
    return res["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
