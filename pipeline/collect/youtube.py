"""YouTube comments on haul / review / try-on videos.

Uniquely captures C14 (off-platform verification exit): people who left
Myntra to watch a haul before deciding are, by definition, already on
YouTube. Their comments are the only direct trace of that behaviour.

`architecture.md` §5.1 designated Reddit the primary reasoning source; with
Reddit reachable only through a third party, YouTube carries more of that
load. Search terms are therefore chosen to surface DELIBERATION ("worth
buying?", "before you buy", "quality check") rather than reaction.

Quota: 10,000 units/day. search=100 units, commentThreads=1 unit. So the
searches, not the comments, are the scarce resource -- hence few queries
and many comments per video.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.collect import base  # noqa: E402
from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402

SOURCE = "youtube"

QUERIES = [
    "myntra haul review honest",
    "myntra quality check before you buy",
    "myntra try on haul size",
    "is myntra worth buying",
    "myntra vs ajio which is better",
    "myntra return experience",
    "online shopping fashion india size problem",
    "myntra kurta haul review",
]


def collect(api_key: str, *, queries: list[str], per_query: int,
            comments_per_video: int) -> None:
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    con = dbm.init()

    with rmod.Run(con, "collect-youtube", model=None, source=SOURCE,
                  n_queries=len(queries)) as run:
        total, video_yield = 0, {}

        for q in queries:
            try:
                res = yt.search().list(
                    q=q, part="snippet", type="video", maxResults=per_query,
                    regionCode="IN", relevanceLanguage="en",
                ).execute()
            except Exception as e:                      # noqa: BLE001
                print(f"  query {q!r}: SEARCH ERROR {type(e).__name__} -- recorded", flush=True)
                continue

            vids = [(i["id"]["videoId"], i["snippet"]["title"]) for i in res.get("items", [])]
            print(f"  query {q!r}: {len(vids)} videos", flush=True)

            for vid, title in vids:
                rows, token, got = [], None, 0
                while got < comments_per_video:
                    try:
                        cr = yt.commentThreads().list(
                            part="snippet", videoId=vid, maxResults=100,
                            textFormat="plainText", order="relevance",
                            pageToken=token,
                        ).execute()
                    except Exception as e:              # noqa: BLE001
                        # EC-COL-2: comments disabled is a per-video ZERO that
                        # gets LOGGED, never skipped quietly.
                        msg = type(e).__name__
                        video_yield[vid] = f"0 ({msg})"
                        break

                    items = cr.get("items", [])
                    if not items:
                        break
                    for it in items:
                        s = it["snippet"]["topLevelComment"]["snippet"]
                        rec = base.make_record(
                            source=SOURCE,
                            native_id=it["snippet"]["topLevelComment"]["id"],
                            source_url=f"https://www.youtube.com/watch?v={vid}"
                                       f"&lc={it['snippet']['topLevelComment']['id']}",
                            text_raw=(s.get("textOriginal") or "").strip(),
                            author=s.get("authorDisplayName"),
                            created_at=s.get("publishedAt"),
                            thread_context=title,       # the video title is the context
                            collect_query=q,
                            ingest_run_id=run.run_id,
                        )
                        if rec:
                            rows.append(rec)
                    got += len(items)
                    token = cr.get("nextPageToken")
                    if not token:
                        break

                n = base.write_records(con, rows)
                total += n
                if vid not in video_yield:
                    video_yield[vid] = str(n)

        run.n_output = total
        zeros = [v for v, n in video_yield.items() if n.startswith("0")]
        print(f"\n  total youtube records: {total}")
        print(f"  videos contributing 0 (logged, not skipped): {len(zeros)}/{len(video_yield)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=6)
    ap.add_argument("--comments-per-video", type=int, default=200)
    ap.add_argument("--queries", nargs="*", default=QUERIES)
    a = ap.parse_args()
    v = envm.load()
    base._SALT = v.get("AUTHOR_SALT", "")
    if not base._SALT:
        sys.exit("AUTHOR_SALT not set (NFR-7)")
    collect(v["YOUTUBE_API_KEY"], queries=a.queries,
            per_query=a.per_query, comments_per_video=a.comments_per_video)
