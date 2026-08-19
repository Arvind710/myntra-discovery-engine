"""Google Play reviews via `google-play-scraper`.

Highest volume source, LOWEST relevance yield -- Play reviews are dominated
by delivery, refund, and app-crash complaints that the relevance rubric
excludes (EC-COL-13). Collected wide on purpose: at an unknown yield rate,
we collect generously and let the filters cut down, logging everything cut
(FR-1.6).

Sorted NEWEST rather than by relevance: Play's relevance sort surfaces
highly-rated promotional text, which skews the corpus toward exactly the
records the analysis will discard.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.collect import base  # noqa: E402
from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402

SOURCE = "play"
APP = "com.myntra.android"
COUNTRY = "in"
LANGS = ["en", "hi"]      # 'hi' surfaces Devanagari and some Hinglish


def collect(target: int = 3000) -> None:
    from google_play_scraper import Sort, reviews

    con = dbm.init()
    with rmod.Run(con, "collect-play", model=None, source=SOURCE,
                  app=APP, country=COUNTRY, target=target) as run:
        total = 0
        for lang in LANGS:
            token, got, page = None, 0, 0
            while got < target // len(LANGS):
                try:
                    batch, token = reviews(
                        APP, lang=lang, country=COUNTRY,
                        sort=Sort.NEWEST, count=200,
                        continuation_token=token,
                    )
                except Exception as e:                  # noqa: BLE001
                    # EC-COL-3: a rate-limited run is never silently treated
                    # as complete -- the partial count is reported.
                    print(f"  {lang}: ERROR {type(e).__name__} at page {page} "
                          f"-- keeping {got} collected so far", flush=True)
                    break
                if not batch:
                    break
                page += 1

                rows = []
                for r in batch:
                    rec = base.make_record(
                        source=SOURCE,
                        native_id=r.get("reviewId", ""),
                        source_url=(f"https://play.google.com/store/apps/details"
                                    f"?id={APP}&reviewId={r.get('reviewId','')}"),
                        text_raw=(r.get("content") or "").strip(),
                        author=r.get("userName"),
                        created_at=r.get("at"),
                        rating=r.get("score"),
                        thread_context=f"Play Store review ({COUNTRY.upper()}/{lang})",
                        collect_query=f"play/{COUNTRY}/{lang}/newest",
                        ingest_run_id=run.run_id,
                    )
                    if rec:
                        rows.append(rec)

                n = base.write_records(con, rows)
                got += n
                total += n
                print(f"  {lang} page {page}: {len(batch)} reviews -> {n} records "
                      f"({got} for this lang)", flush=True)
                if not token:
                    break

        run.n_output = total
        print(f"\n  total play records: {total}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=3000)
    a = ap.parse_args()
    v = envm.load()
    base._SALT = v.get("AUTHOR_SALT", "")
    if not base._SALT:
        sys.exit("AUTHOR_SALT not set (NFR-7)")
    collect(a.target)
