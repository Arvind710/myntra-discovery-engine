"""iOS App Store reviews via Apple's first-party RSS customer-review feed.

No auth, no scraping, no third party -- this is a documented endpoint Apple
publishes. (The `app-store-scraper` package was tried and rejected: it is
unmaintained and pins requests<2.24, which breaks streamlit and
google-api-core in the same environment.)

EXPECT LOW RELEVANCE YIELD. App-store reviews skew bimodal (1-star and
5-star) and toward transactional failures -- delivery, refunds, crashes,
customer care -- which the relevance rubric excludes by design (EC-COL-13).
That low yield is a MEASUREMENT, reported in the pilot, not a failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.collect import base  # noqa: E402
from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402

SOURCE = "appstore"
APP_ID = "907394059"          # Myntra, iOS
COUNTRY = "in"
FEED = ("https://itunes.apple.com/{c}/rss/customerreviews/page={p}"
        "/id={a}/sortby=mostrecent/json")
MAX_PAGE = 10                  # Apple caps the feed at ~10 pages / 500 reviews


def fetch_page(page: int) -> list[dict]:
    url = FEED.format(c=COUNTRY, p=page, a=APP_ID)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.loads(r.read())
    entries = data.get("feed", {}).get("entry", [])
    # Entry 0 is the app itself, not a review -- only when the feed has one.
    return [e for e in entries if "im:rating" in e]


def collect(pages: int = MAX_PAGE) -> None:
    con = dbm.init()
    with rmod.Run(con, "collect-appstore", model=None, source=SOURCE,
                  app_id=APP_ID, country=COUNTRY) as run:
        total, seen_empty = 0, 0
        for p in range(1, pages + 1):
            try:
                entries = fetch_page(p)
            except Exception as e:                      # noqa: BLE001
                print(f"  page {p}: ERROR {type(e).__name__} -- recorded, continuing", flush=True)
                continue

            if not entries:
                seen_empty += 1
                print(f"  page {p}: 0 reviews", flush=True)
                if seen_empty >= 2:
                    break
                continue

            rows = []
            for e in entries:
                title = e.get("title", {}).get("label", "")
                body = e.get("content", {}).get("label", "")
                text = f"{title}. {body}".strip(". ") if title else body
                rec = base.make_record(
                    source=SOURCE,
                    native_id=e.get("id", {}).get("label", ""),
                    source_url=e.get("link", {}).get("attributes", {}).get(
                        "href", f"https://apps.apple.com/{COUNTRY}/app/id{APP_ID}"),
                    text_raw=text,
                    author=e.get("author", {}).get("name", {}).get("label"),
                    created_at=e.get("updated", {}).get("label"),
                    rating=int(e.get("im:rating", {}).get("label", 0)) or None,
                    thread_context=f"App Store review ({COUNTRY.upper()})",
                    collect_query=f"appstore/{COUNTRY}/page{p}",
                    ingest_run_id=run.run_id,
                )
                if rec:
                    rows.append(rec)
            n = base.write_records(con, rows)
            total += n
            print(f"  page {p}: {len(entries)} entries -> {n} records", flush=True)

        run.n_output = total
        print(f"\n  total appstore records: {total}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=MAX_PAGE)
    a = ap.parse_args()
    v = envm.load()
    base._SALT = v.get("AUTHOR_SALT", "")
    if not base._SALT:
        sys.exit("AUTHOR_SALT not set (NFR-7)")
    collect(a.pages)
