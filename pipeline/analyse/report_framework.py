"""Report engine results in the UPDATED FRAMEWORK's codes.

Everything the engine computed is translated through crosswalk_v2.yaml
before it is displayed. Nothing maps a code by hand in a query: engine C9 is
framework C10, and a number reported under the wrong label would look right
and mean something else.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CW = yaml.safe_load((ROOT / "codebook" / "crosswalk_v2.yaml").read_text())
MAP = CW["engine_to_framework"]
NAMES = {k: v.get("name", "") for k, v in CW["stage_c"].items()}


def to_framework(code: str) -> tuple[str, str]:
    """engine code -> (framework code, note)"""
    m = MAP.get(code)
    if not m:
        return code, ""          # Stage A/B/D are unchanged
    return m["to"], str(m.get("note", ""))


def main() -> None:
    con = dbm.connect()

    print("=" * 66)
    print("BARRIER PREVALENCE — reported in the updated framework's codes")
    print("=" * 66)
    print(f"{'code':<7}{'n':>5}{'auth':>6}{'share':>8}  name / translation note")
    rows = list(con.execute(
        "SELECT * FROM analysis_code_prevalence WHERE n > 0 AND stage='C' ORDER BY n DESC"))
    for r in rows:
        fw, note = to_framework(r["code"])
        nm = NAMES.get(fw.split(".")[0], "")
        flag = "" if not note or note == "direct" else f"   [engine {r['code']} -> {fw}]"
        print(f"{fw:<7}{r['n']:>5}{r['n_distinct_authors']:>6}{r['share']:>7.1%}  {nm}{flag}")

    print()
    print("=" * 66)
    print("SIX SEGMENTS  (100% coverage — derived, not inferred)")
    print("=" * 66)
    for r in con.execute("""SELECT segment_id, segment_name, count(*) n
                            FROM segments_v2 GROUP BY segment_id ORDER BY segment_id"""):
        star = "  <-- TARGET" if r["segment_id"] == 4 else ""
        print(f"  {r['segment_id']}. {r['segment_name']:<20}{r['n']:>5}"
              f"{r['n']/1199:>8.1%}{star}")

    print()
    print("=" * 66)
    print("STUCK DECIDERS — barrier profile (the target segment)")
    print("=" * 66)
    tot = con.execute("SELECT count(*) FROM segments_v2 WHERE segment_id=4").fetchone()[0]
    print(f"  n = {tot} records\n")
    print(f"  {'code':<7}{'n':>5}{'auth':>6}{'of seg':>9}   name")
    for r in con.execute("""SELECT * FROM analysis_segment_code_v2
                            WHERE segment_id = 4 AND n >= 15 ORDER BY n DESC LIMIT 12"""):
        fw, _ = to_framework(r["code"])
        nm = NAMES.get(fw.split(".")[0], "")
        print(f"  {fw:<7}{r['n']:>5}{r['n_distinct_authors']:>6}{r['share']:>8.1%}   {nm}")

    print()
    print("  Compared with the corpus overall — what is DISTINCTIVE about them:")
    overall = {r["code"]: r["share"] for r in
               con.execute("SELECT code, share FROM analysis_code_prevalence")}
    lifts = []
    for r in con.execute("SELECT * FROM analysis_segment_code_v2 WHERE segment_id=4 AND n>=20"):
        base = overall.get(r["code"], 0)
        if base:
            lifts.append((r["share"] / base, r["code"], r["n"], r["share"], base))
    for lift, code, n, s, b in sorted(lifts, reverse=True)[:6]:
        fw, _ = to_framework(code)
        print(f"    {fw:<7} {lift:>5.2f}x   {s:.1%} of segment vs {b:.1%} of corpus  (n={n})")


if __name__ == "__main__":
    main()
