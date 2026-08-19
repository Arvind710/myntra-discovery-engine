"""Myntra on-platform product reviews (FR-1.1: "on-platform product reviews
and Q&A where accessible").

ROBOTS-PERMITTED. Myntra's robots.txt is `User-agent: * / Allow: /` with 729
disallow rules, none covering product or review paths (checked 2026-08-19;
the only `/buy` rule is `*/buy1-get1-offer/*`). Reviews are embedded in the
product page's own `window.__myx` state -- no auth, no internal API.

WHAT THIS SOURCE IS FOR, and it is not what it looks like.

These are POST-purchase reviews, which the relevance rubric largely
excludes. Their value is different and specific: they ARE the content that
code C4 ("real-buyer evidence insufficient") is a complaint about. Users
say on Reddit that on-platform reviews are thin, stale, and photo-less;
this collector lets that be MEASURED rather than inferred.

The page-level aggregates are the finding here as much as the review text:
a sampled product carried 13,460 reviews of which 2,434 (18%) had images,
while the page surfaced only 3. That is a quantified C4 result no complaint
corpus can produce.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.collect import base  # noqa: E402
from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402

SOURCE = "myntra"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
STATE = re.compile(r"window\.__myx\s*=\s*(\{.*?\});?\s*</script>", re.S)

# Categories where fit / fabric / styling uncertainty actually bites --
# the C1/C2/C3 territory. Electronics-style catalogue pages would add
# volume and no signal.
SEARCH_TERMS = ["kurta", "dress", "jeans", "tshirt", "top", "shirt", "saree", "kurta-set"]

DELAY_S = 1.5   # deliberate rate limiting -- permitted is not the same as unlimited


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_state(html: str) -> dict | None:
    m = STATE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def product_urls_from_search(term: str, limit: int) -> list[tuple[str, str]]:
    """Return (product_id, path). Myntra product URLs are
    /{category}/{brand}/{slug}/{id}/buy -- the bare id 404s. The search
    page carries the real path in `landingPageUrl`, unicode-escaped."""
    html = _get(f"https://www.myntra.com/{term}")
    paths = re.findall(r'"landingPageUrl"\s*:\s*"([^"]+)"', html)
    seen, out = set(), []
    for raw in paths:
        path = raw.encode().decode("unicode_escape")
        m = re.search(r"/(\d{5,10})/buy$", path)
        if not m:
            continue
        pid = m.group(1)
        if pid in seen:
            continue
        seen.add(pid)
        out.append((pid, path))
        if len(out) >= limit:
            break
    return out


def collect_product(pid: str, path: str, term: str, run_id: str) -> tuple[list[dict], dict | None]:
    """Return (review_records, aggregate_stats)."""
    url = f"https://www.myntra.com/{path.lstrip('/')}"
    html = _get(url)
    state = parse_state(html)
    if not state:
        return [], None

    pdp = state.get("pdpData") or {}
    ratings = pdp.get("ratings") or {}
    info = ratings.get("reviewInfo") or {}
    name = pdp.get("name") or pdp.get("brand", {}).get("name") or f"product {pid}"

    n_reviews = int(str(info.get("reviewsCount") or 0) or 0)
    n_images = int(str(info.get("reviewsImageCount") or 0) or 0)
    top = info.get("topReviews") or []

    stats = {
        "product_id": pid, "name": name, "term": term,
        "avg_rating": ratings.get("averageRating"),
        "reviews_total": n_reviews,
        "reviews_with_images": n_images,
        "reviews_surfaced": len(top),
    }

    rows = []
    for r in top:
        text = (r.get("review") or r.get("reviewText") or "").strip()
        rid = r.get("id") or r.get("reviewId") or f"{pid}-{abs(hash(text)) % 10**8}"
        rec = base.make_record(
            source=SOURCE,
            native_id=str(rid),
            source_url=url,
            text_raw=text,
            author=r.get("userName") or r.get("name"),
            created_at=r.get("createdAt") or r.get("date"),
            rating=r.get("userRating") or r.get("rating"),
            thread_context=f"Myntra product review | {name}",
            collect_query=f"myntra/{term}",
            ingest_run_id=run_id,
        )
        if rec:
            rows.append(rec)
    return rows, stats


def collect(products_per_term: int) -> None:
    con = dbm.init()
    with rmod.Run(con, "collect-myntra", model=None, source=SOURCE,
                  terms=len(SEARCH_TERMS)) as run:
        total, all_stats = 0, []

        for term in SEARCH_TERMS:
            try:
                pids = product_urls_from_search(term, products_per_term)
            except Exception as e:                      # noqa: BLE001
                print(f"  {term}: SEARCH ERROR {type(e).__name__} -- recorded", flush=True)
                continue
            print(f"  {term}: {len(pids)} products", flush=True)

            for pid, path in pids:
                try:
                    rows, stats = collect_product(pid, path, term, run.run_id)
                except Exception as e:                  # noqa: BLE001
                    print(f"    {pid}: {type(e).__name__}", flush=True)
                    time.sleep(DELAY_S)
                    continue
                if stats:
                    all_stats.append(stats)
                total += base.write_records(con, rows)
                time.sleep(DELAY_S)

        run.n_output = total

        # The aggregate IS the C4 finding -- persisted alongside the text.
        out = Path(__file__).resolve().parents[2] / "data" / "artifacts"
        out.mkdir(parents=True, exist_ok=True)
        (out / "myntra_review_coverage.json").write_text(json.dumps(all_stats, indent=2))

        print(f"\n  total myntra review records: {total}")
        if all_stats:
            tot = sum(s["reviews_total"] for s in all_stats)
            img = sum(s["reviews_with_images"] for s in all_stats)
            shown = sum(s["reviews_surfaced"] for s in all_stats)
            print(f"  products sampled            : {len(all_stats)}")
            print(f"  reviews existing (claimed)  : {tot:,}")
            print(f"  with images                 : {img:,} ({img/max(tot,1):.1%})")
            print(f"  surfaced on the page        : {shown:,} ({shown/max(tot,1):.3%})")
            print("  ^ this ratio is the C4 evidence-thinness measurement")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--products-per-term", type=int, default=8)
    a = ap.parse_args()
    v = envm.load()
    base._SALT = v.get("AUTHOR_SALT", "")
    if not base._SALT:
        sys.exit("AUTHOR_SALT not set (NFR-7)")
    collect(a.products_per_term)
