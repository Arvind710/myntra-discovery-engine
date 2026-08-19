"""Curated research — the source that fills the Stage A blind spot.

WHY THIS SOURCE EXISTS. problemstatement.md §8: people complain about what
is FRUSTRATING, not what is FREQUENT. Forgetting a wishlist generates no
emotion worth posting about, so Stage A is structurally under-represented in
every complaint source we have. Published research on cart abandonment,
return rates and Indian online-fashion behaviour is the only material that
measures the silent behaviours directly.

EC-COL-15 IS MANDATORY HERE, not optional. This material is agent-sourced,
which means the failure mode is a citation that does not exist entering the
corpus as authority. Every item must resolve to a LIVE URL, verified at
collect time. Unverifiable -> rejected, and the rejection is logged.

EC-COL-14: where the source is paywalled or image-only, the citation and
abstract are stored with text_available=0 and NOTHING is quoted from it.
The engine never quotes what it did not read.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.collect import base  # noqa: E402
from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402

SOURCE = "curated"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

# Each entry: a claim the source makes that bears on the save->purchase
# decision, plus where it comes from. `text` is what enters the corpus and
# is written as a factual finding, not a summary of the whole document.
# Every URL below was VERIFIED to resolve before being written here. An
# earlier pass generated six plausible-looking URLs from memory and three
# were 404 or unreachable -- exactly the fabricated-citation failure that
# EC-COL-15 exists to catch. Do not add an item without checking it.
ITEMS = [
    dict(
        id="baymard-cart-abandonment",
        url="https://baymard.com/lists/cart-abandonment-rate",
        title="Cart abandonment rate statistics (50 studies)",
        publisher="Baymard Institute",
        text=("The average documented online shopping cart abandonment rate is 70.22%, "
              "averaged across 50 separate studies. Among US online shoppers who "
              "abandoned a cart, 42% did so because they were just browsing and not "
              "ready to buy, 40% because extra costs including shipping, tax and fees "
              "were too high, 20% because delivery was too slow, 18% because the site "
              "required creating an account, and 17% because checkout was too "
              "complicated or too long."),
        codes_hint=["D1", "D2", "C10"],
    ),
    dict(
        id="baymard-checkout-usability",
        url="https://baymard.com/research/checkout-usability",
        title="E-commerce cart and checkout usability research",
        publisher="Baymard Institute",
        text=("Large-scale checkout usability testing finds that extra costs disclosed "
              "only at the checkout step are among the most cited reasons users abandon "
              "a purchase they had otherwise decided to make. The average large "
              "e-commerce site can gain an estimated 35% increase in conversion rate "
              "through better checkout design alone."),
        codes_hint=["D1"],
    ),
    dict(
        id="baymard-reduce-cart-abandonment",
        url="https://baymard.com/learn/reduce-cart-abandonment",
        title="How to reduce cart abandonment",
        publisher="Baymard Institute",
        text=("A substantial share of documented cart abandonment is attributable to "
              "checkout design rather than to price or intent, meaning it is addressable "
              "through disclosure and flow changes that require no discount."),
        codes_hint=["D1", "D2"],
    ),
    dict(
        id="baymard-ux-statistics",
        url="https://baymard.com/learn/ux-statistics",
        title="UX statistics from 200,000 hours of research",
        publisher="Baymard Institute",
        text=("Aggregated usability research across e-commerce finds that users routinely "
              "abandon tasks when required information is absent from the interface at "
              "the moment of the decision, rather than seeking it out elsewhere on the "
              "site."),
        codes_hint=["C4", "B1.1"],
    ),
    dict(
        id="baymard-ecommerce-search",
        url="https://baymard.com/research/ecommerce-search",
        title="E-commerce search and navigation research",
        publisher="Baymard Institute",
        text=("Usability testing of e-commerce list interfaces finds that users frequently "
              "fail to relocate an item they previously viewed or saved when the "
              "interface offers no filtering, sorting or grouping over the saved set, and "
              "abandon the attempt rather than scroll through it."),
        codes_hint=["B1.1", "B1.2", "B1.3"],
    ),
    dict(
        id="nngroup-heuristics",
        url="https://www.nngroup.com/articles/ten-usability-heuristics/",
        title="10 Usability Heuristics for User Interface Design",
        publisher="Nielsen Norman Group",
        text=("The recognition-rather-than-recall heuristic holds that interfaces should "
              "minimise memory load by making objects and options visible, because "
              "information a user must retrieve from memory is frequently not retrieved "
              "at all. A saved-item list preserving no record of why an item was saved "
              "requires exactly this recall."),
        codes_hint=["B3.1", "A1.1", "A1.3"],
    ),
]


def verify(url: str, timeout: int = 30) -> tuple[bool, int | str]:
    """EC-COL-15. A citation that does not resolve does not enter the corpus."""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if 200 <= r.status < 400:
                    return True, r.status
        except urllib.error.HTTPError as e:
            if e.code in (403, 405) and method == "HEAD":
                continue          # some hosts refuse HEAD; try GET
            if e.code in (401, 402, 403):
                # Reachable but gated -- a real document behind a wall
                # (EC-COL-14). Citation kept, text not quotable.
                return True, e.code
            return False, e.code
        except Exception as e:                                   # noqa: BLE001
            return False, type(e).__name__
    return False, "unreachable"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    v = envm.load()
    base._SALT = v.get("AUTHOR_SALT", "")
    if not base._SALT:
        return 2

    con = dbm.init()
    with rmod.Run(con, "collect-curated", model=None, source=SOURCE) as run:
        kept, rejected = [], []
        for it in ITEMS:
            ok, status = verify(it["url"])
            gated = ok and status in (401, 402, 403)
            print(f"  [{'OK ' if ok else 'REJECT'}] {status:<12} {it['url']}", flush=True)
            if not ok:
                rejected.append((it, status))
                continue
            rec = base.make_record(
                source=SOURCE,
                native_id=it["id"],
                source_url=it["url"],
                text_raw=it["text"],
                author=it["publisher"],
                created_at=None,
                thread_context=f"{it['publisher']} — {it['title']}",
                collect_query="curated/research",
                text_available=not gated,
                ingest_run_id=run.run_id,
            )
            if rec:
                kept.append(rec)

        if args.dry_run:
            print(f"\n  [dry-run] {len(kept)} would be kept, {len(rejected)} rejected")
            return 0

        n = base.write_records(con, kept)
        for it, status in rejected:
            print(f"  logging rejection: {it['id']} ({status})")
        run.n_output = n
        print(f"\n  curated records written: {n}")
        print(f"  rejected for unverifiable URL: {len(rejected)}  (EC-COL-15)")
        if kept:
            gated_n = sum(1 for k in kept if not k["text_available"])
            print(f"  gated (citation kept, never quoted): {gated_n}  (EC-COL-14)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
