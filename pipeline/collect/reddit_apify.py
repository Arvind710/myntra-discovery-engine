"""Reddit collector via the Apify `webdatalabs/reddit-scraper-pro` actor.

WHY THIS EXISTS. Reddit's own API is unavailable to this project: the
application was rejected, the self-serve script-app path is closed to new
developers as of 2026, and every unauthenticated endpoint is blocked
(www .json -> 403; old .json -> a block page; RSS -> an empty feed;
robots.txt -> `Disallow: /`). Reddit for Researchers is the sanctioned
route but runs to months.

Reddit was the design's designated source for long-form "why I didn't buy"
reasoning (`architecture.md` §5.1) -- the only source that captures
deliberation rather than reaction. Losing it costs counterfactuals and
multi-barrier records, which are two of the highest-signal analytics in the
project.

COLLECTION METHOD IS DISCLOSED, NOT HIDDEN. `collect_method` is stamped on
every row and surfaced in the corpus composition dashboard and the deck.
A stated method chosen deliberately is defensible; one that is discovered
is not. See DECISIONS.md for the full reasoning and the alternatives that
were tested and rejected.

Actor: pay-per-event, no monthly rental. Free-plan credits ($5/mo) cover
roughly 1.5-4k results depending on tier.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.collect import base  # noqa: E402
from pipeline.common import db as dbm  # noqa: E402
from pipeline.common import runs as rmod  # noqa: E402

ACTOR = "webdatalabs~reddit-scraper-pro"
API = "https://api.apify.com/v2"
SOURCE = "reddit"

# Communities where Indian fashion-shopping deliberation actually happens.
SUBREDDITS = [
    "IndianFashionAddicts", "IndianFashion", "DesiFashion",
    "TwoXIndia", "india", "IndiaTech", "bangalore", "mumbai", "delhi",
]

# Phrasings that surface the SAVE -> PURCHASE gap specifically, rather than
# generic Myntra complaints. Every query is stored on the record it produced
# (`collect_query`), so a theme's prevalence can later be audited against the
# search terms that found it (EC-COL-12).
QUERIES = [
    "myntra wishlist",
    "myntra saved items",
    "wishlist never buy",
    "saved for later never bought",
    "myntra size not sure",
    "myntra return experience buying",
    "online shopping wishlist fashion india",
    "myntra vs ajio sizing",
    "should i buy myntra",
    "myntra haul disappointed",
]


def _post(url: str, payload: dict, token: str) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def _get(url: str, token: str) -> Any:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def run_actor(token: str, payload: dict, *, poll_s: int = 10, timeout_s: int = 1800) -> list[dict]:
    """Start the actor, poll to completion, return dataset items."""
    run = _post(f"{API}/acts/{ACTOR}/runs", payload, token)["data"]
    run_id, ds_id = run["id"], run["defaultDatasetId"]
    print(f"    apify run {run_id} started", flush=True)

    waited = 0
    while waited < timeout_s:
        time.sleep(poll_s)
        waited += poll_s
        status = _get(f"{API}/actor-runs/{run_id}", token)["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            print(f"    status {status} after {waited}s", flush=True)
            if status != "SUCCEEDED":
                # EC-COL-3: a partial run is never silently treated as complete.
                print(f"    WARNING: non-success status, keeping partial results", flush=True)
            break
    else:
        raise TimeoutError(f"actor run {run_id} exceeded {timeout_s}s")

    return _get(f"{API}/datasets/{ds_id}/items?clean=true&format=json", token)


def to_records(items: list[dict], query: str, ingest_run_id: str) -> Iterator[dict]:
    """Map actor output onto the `records` schema.

    Both POSTS and COMMENTS become records. Comments matter more than posts
    here: a post asks a question, the comments carry the reasoning.
    """
    for it in items:
        kind = (it.get("dataType") or it.get("type") or "post").lower()
        is_comment = "comment" in kind

        text = it.get("body") or it.get("selftext") or it.get("text") or ""
        title = it.get("title") or ""
        # A post's title carries real signal ("why do I never buy from my
        # wishlist?"), so it is prepended rather than discarded.
        if not is_comment and title:
            text = f"{title}\n\n{text}".strip()

        native = it.get("id") or it.get("commentId") or it.get("postId")
        url = it.get("url") or it.get("permalink") or it.get("link")
        if url and url.startswith("/"):
            url = f"https://www.reddit.com{url}"
        if not native or not url:
            continue

        rec = base.make_record(
            source=SOURCE,
            native_id=str(native),
            source_url=url,
            text_raw=text,
            author=it.get("username") or it.get("author"),
            created_at=it.get("createdAt") or it.get("created_utc") or it.get("created"),
            thread_context=(it.get("parentPostTitle") or title or None),
            collect_query=query,
            ingest_run_id=ingest_run_id,
        )
        if rec:
            yield rec


def collect(token: str, *, max_per_target: int, comment_depth: int,
            queries: list[str], subreddits: list[str], dry_run: bool = False) -> None:
    con = dbm.init()
    with rmod.Run(con, "collect-reddit", model=None, source=SOURCE,
                  actor=ACTOR, collect_method="apify",
                  max_per_target=max_per_target) as run:
        total = 0
        yields: dict[str, int] = {}

        for query in queries:
            payload = {
                "searchMode": "keyword",
                "keywords": [query],
                "subreddits": subreddits,
                "maxItemsPerSubreddit": max_per_target,
                "searchSort": "relevance",
                "includeComments": True,
                "commentDepth": comment_depth,
            }
            print(f"  query {query!r}", flush=True)
            if dry_run:
                print(f"    [dry-run] payload: {json.dumps(payload)}", flush=True)
                continue
            try:
                items = run_actor(token, payload)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
                # EC-COL-3 / AR-1: never let a failed query look like a zero yield.
                print(f"    ERROR {type(e).__name__}: {e} -- recorded, continuing", flush=True)
                yields[query] = -1
                continue

            rows = list(to_records(items, query, run.run_id))
            n = base.write_records(con, rows)
            yields[query] = n
            total += n
            print(f"    {len(items)} items -> {n} records", flush=True)

        run.n_output = total
        print(f"\n  total reddit records: {total}")
        print("  per-query yield (a zero is a finding, not a skip):")
        for q, n in yields.items():
            print(f"    {n:>6}  {q}" + ("   <- FAILED" if n < 0 else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-per-target", type=int, default=25,
                    help="posts per (query, subreddit). Keep low on the free tier")
    ap.add_argument("--comment-depth", type=int, default=2)
    ap.add_argument("--queries", nargs="*", default=QUERIES)
    ap.add_argument("--subreddits", nargs="*", default=SUBREDDITS)
    ap.add_argument("--dry-run", action="store_true",
                    help="print payloads without spending credits")
    args = ap.parse_args()

    for line in (Path(__file__).resolve().parents[2] / ".env").read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
    base._SALT = os.environ.get("AUTHOR_SALT", "")

    token = os.environ.get("APIFY_TOKEN", "")
    if not token and not args.dry_run:
        print("APIFY_TOKEN not set. Add it to .env — see DECISIONS.md.", file=sys.stderr)
        return 2

    collect(token, max_per_target=args.max_per_target, comment_depth=args.comment_depth,
            queries=args.queries, subreddits=args.subreddits, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
