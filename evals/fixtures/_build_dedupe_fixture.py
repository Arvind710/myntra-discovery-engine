"""Emit dedupe_consensus.jsonl for S1-PROBE-1.

The single most important test in Stage 1, because the failure it guards is
invisible (EC-CLEAN-1). Forty people independently saying "sizes run small"
IS the finding. A pipeline that near-dedupes across authors deletes the
strongest evidence in the corpus, and the charts look fine afterwards.

The fixture pins BOTH directions:
  - 40 records, 40 DISTINCT authors, near-identical text  -> all 40 survive
  -  5 records, ONE author, near-identical text           -> 4 removed
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "dedupe_consensus.jsonl"

# Deliberately high lexical overlap. A cross-author Jaccard>0.85 near-dupe
# pass WOULD collapse most of these -- which is exactly the bug being pinned.
CONSENSUS = [
    "The sizes run small on Myntra, I always have to order one size up",
    "Sizes run small here, I always order one size up honestly",
    "sizes run small on myntra so i always order a size up",
    "Sizes run really small, I have to order one size up every time",
    "The sizes run small, always ordering one size up now",
    "Myntra sizes run small, order one size up is my rule",
    "Sizes run small for me, so I order one size larger always",
    "sizes run small here always order one size up guys",
    "Sizes run small on this app, one size up always works",
    "The sizes run quite small, I order one size up now",
    "Sizes run small, I've learned to order one size up",
    "On Myntra the sizes run small so order one size up",
    "Sizes run small yaar, always order one size up",
    "Sizes run small, ordering one size up is the only way",
    "Their sizes run small, I order one size up every single time",
    "Sizes run small in most brands here, order a size up",
    "sizes run small on myntra always order size up trust me",
    "The sizes run small, so I just order one size up",
    "Sizes run small, one size up is what I always do now",
    "Myntra sizes run small only, order one size up",
    "Sizes run small, I always end up ordering one size up",
    "Sizes run small here so ordering one size up is safer",
    "The sizes run small on Myntra, order one size bigger",
    "Sizes run small, always order one size up or it won't fit",
    "sizes run small so i order one size up every time now",
    "Sizes run small, order one size up, learned this the hard way",
    "Sizes run small on Myntra, one size up is standard for me",
    "The sizes run small, I've started ordering one size up",
    "Sizes run small, so order one size up to be safe",
    "Sizes run small here, ordering one size up always",
    "Myntra sizes run small, so I order one size up now",
    "Sizes run small, one size up and it fits fine",
    "Sizes run small on this platform, order one size up",
    "The sizes run small, always go one size up",
    "Sizes run small, I order one size up without thinking now",
    "sizes run small always order one size up on myntra",
    "Sizes run small, so ordering one size up is my default",
    "Sizes run small here, better to order one size up",
    "The sizes run small on Myntra, I order one size up",
    "Sizes run small, one size up every time for me",
]
assert len(CONSENSUS) == 40, len(CONSENSUS)

# Same author, near-identical -- genuine duplication (EC-COL-8 review-farm
# shape). Author-scoped dedupe must collapse these to one.
SAME_AUTHOR = [
    "Great app great products great service highly recommended to everyone",
    "Great app great products great service highly recommended to everyone!",
    "Great app, great products, great service, highly recommended to everyone",
    "Great app great product great service highly recommended to everyone",
    "Great app great products great service highly recommend to everyone",
]

rows = []
for i, text in enumerate(CONSENSUS, start=1):
    rows.append({
        "record_id": f"fx-consensus-{i:03d}",
        "source": "reddit",
        "source_url": f"https://reddit.com/r/IndianFashionAddicts/comments/fx{i:03d}",
        "native_id": f"fx{i:03d}",
        "author_hash": f"author-{i:03d}",          # 40 DISTINCT authors
        "created_at": "2026-05-01T10:00:00+00:00",
        "text_raw": text,
        "expect_survives": True,
        "why": "distinct author expressing shared experience -- this IS the finding",
    })

for i, text in enumerate(SAME_AUTHOR, start=1):
    rows.append({
        "record_id": f"fx-sameauthor-{i:03d}",
        "source": "play",
        "source_url": f"https://play.google.com/store/apps/details?id=com.myntra.android&r=sa{i}",
        "native_id": f"sa{i:03d}",
        "author_hash": "author-repeat-001",         # ONE author
        "created_at": "2026-05-02T10:00:00+00:00",
        "text_raw": text,
        "expect_survives": i == 1,                  # keep the first, drop 4
        "why": "same author repeating near-identical text -- genuine duplication",
    })

OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
print(f"{OUT.name}: {len(rows)} records "
      f"({sum(r['expect_survives'] for r in rows)} expected to survive, "
      f"{len({r['author_hash'] for r in rows})} distinct authors)")
