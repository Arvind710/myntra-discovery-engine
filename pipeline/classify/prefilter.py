"""Prefilter — cheap gate before any LLM sees a record.

UNION, NEVER INTERSECTION. EC-PRE-1 is the silent failure this guards: a
record dropped here never reaches an LLM, never appears in any denominator,
and produces no error and no log entry showing a *wrong* decision. There is
no way to notice it from the output. So recall beats precision here, and
the LLM relevance pass is the precision step.

Every decision is PERSISTED (`prefilter` table), which is what makes
S2-MET-6 measurable: "would the prefilter have kept this gold-relevant
record?" can then be answered without re-running anything.

Two gates:
  lexicon   -- free, high precision on explicit save/wishlist language
  embedding -- free at read time (offline, ~$0.02 for the whole corpus),
               catches records that describe the behaviour without using
               any of the keywords
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.common import db as dbm, env as envm, runs as rmod  # noqa: E402

EMBED_MODEL = "text-embedding-3-small"
EMBED_TOP_FRACTION = 0.45     # keep the top N% by similarity
EMBED_MIN_SIM = 0.28

# --- lexicon gate -------------------------------------------------------
# Deliberately broad. A term that admits noise costs one LLM call; a term
# that is missing costs a record nobody will ever know was lost.
LEXICON = [
    r"wish\s?list", r"wishlisted", r"saved? (?:it |them |this )?for later",
    r"save[ds]? (?:it|this|them)", r"add(?:ed)? to (?:bag|cart)", r"my list",
    r"bookmark", r"favourite[ds]?", r"favorite[ds]?",
    r"(?:haven'?t|never|didn'?t) (?:bought|ordered|purchased|buy)",
    r"thinking of buying", r"planning to buy", r"about to (?:buy|order)",
    r"should i (?:buy|order|get)", r"still (?:haven'?t|hesitat)",
    r"keep(?:s)? (?:looking|coming back)", r"waiting for (?:a )?(?:sale|discount|price)",
    r"price drop", r"back in stock", r"out of stock", r"sold out",
    r"which size", r"size chart", r"true to size", r"runs? (?:small|large|big)",
    r"fit(?:ting)? (?:issue|problem|doubt)", r"return polic", r"exchange",
    r"before (?:i )?(?:buy|order)", r"worth (?:buying|it)",
    r"compare|comparing", r"cart", r"checkout",
    # Hinglish -- the corpus is code-mixed and English-only patterns miss it
    r"order (?:nahi|nhi)", r"khareed", r"lena hai", r"leni hai",
    r"size ka", r"paisa", r"sasta", r"mehnga", r"bharosa",
]
LEX_RE = re.compile("|".join(LEXICON), re.I)

# --- embedding gate exemplars ------------------------------------------
# Hand-written descriptions of save-then-hesitate behaviour. These define
# the semantic neighbourhood, so they describe the BEHAVIOUR rather than
# naming the platform.
EXEMPLARS = [
    "I saved this dress weeks ago but I still haven't bought it",
    "my wishlist is full of things I never end up ordering",
    "I keep going back to look at it but I don't press buy",
    "I'm not sure which size to pick so I haven't ordered",
    "the fabric might not look like the photos so I'm hesitating",
    "I want to see what real buyers said before I order",
    "I left the app to watch a review video and never came back",
    "waiting for a sale before I buy the thing I saved",
    "I need to ask my husband before spending this much",
    "there are five similar options and I can't decide which one",
    "my size went out of stock before I could order it",
    "returns are such a hassle that I don't risk buying",
    "I forgot I had even saved anything in that list",
    "I can't find the item I saved last month in my list",
    "half the things in my saved list are sold out now",
    "I don't remember why I saved this item",
    "the shipping fee at checkout made me abandon the order",
    "I added it to my bag but never completed the payment",
    "I just save things for inspiration, I don't plan to buy",
    "I bought it somewhere else instead",
    "I lost interest in the item after a few weeks",
    "nothing prompted me to actually buy it today",
    "I screenshot items to compare with what I already own",
    "I ordered two sizes because I wasn't sure of the fit",
    "I check the price on other sites before buying",
    "the reviews had no photos so I couldn't judge the quality",
    "delivery date was too late for the occasion so I cancelled",
    "the item turned out to be non-returnable at checkout",
    "will this suit my body type or should I skip it",
    "I'm saving it for a wedding later this year",
    "size chart says one thing but reviews say it runs small",
    "colour looked different from the picture in other reviews",
    "I keep this in my cart as a holding pen",
    "I wanted it but the price went up since I saved it",
    "payment kept failing so I gave up on the order",
    "I asked in the comments whether it fits true to size",
    "brand sizing is so inconsistent I never know what to order",
    "I look at it every week and still don't buy",
    "not sure if the quality justifies the price",
    "I want to see it on someone with my body type first",
    "wishlist mein bahut items hain lekin order nahi karti",
    "size ka confusion hai isliye nahi mangwaya",
    "sale ka wait kar rahi hoon phir lungi",
    "photo se fabric alag lagta hai isliye dar lagta hai",
    "return karna itna mushkil hai ki order hi nahi karti",
    "I abandoned the purchase at the last step",
    "it's been in my saved items for months",
    "I browse and save but rarely check out",
    "someone said it runs small so now I'm unsure",
    "I want to be certain before I spend that much",
]


def lexicon_hits(texts: list[str]) -> np.ndarray:
    return np.array([bool(LEX_RE.search(t)) for t in texts])


def embed(client, texts: list[str], batch: int = 256) -> np.ndarray:
    out = []
    for i in range(0, len(texts), batch):
        chunk = [t[:6000] for t in texts[i:i + batch]]
        r = client.embeddings.create(model=EMBED_MODEL, input=chunk)
        out.extend(d.embedding for d in r.data)
        print(f"    embedded {min(i + batch, len(texts))}/{len(texts)}", flush=True)
    a = np.array(out, dtype=np.float32)
    return a / np.clip(np.linalg.norm(a, axis=1, keepdims=True), 1e-9, None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-embed", action="store_true", help="lexicon gate only")
    args = ap.parse_args()

    v = envm.load()
    con = dbm.connect()
    rows = [dict(r) for r in con.execute(
        "SELECT record_id, source, text_clean FROM retained")]
    texts = [r["text_clean"] for r in rows]
    print(f"prefiltering {len(rows)} retained records\n")

    lex = lexicon_hits(texts)
    print(f"  lexicon gate : {int(lex.sum())} hits ({lex.mean():.1%})")

    sims = np.zeros(len(rows), dtype=np.float32)
    emb_hit = np.zeros(len(rows), dtype=bool)

    if not args.no_embed:
        from openai import OpenAI
        client = OpenAI(api_key=v["OPENAI_API_KEY"], timeout=120.0)
        with rmod.Run(con, "embed-prefilter", model=EMBED_MODEL) as run:
            print("  embedding exemplars…", flush=True)
            ex = embed(client, EXEMPLARS)
            print("  embedding corpus…", flush=True)
            E = embed(client, texts)
            run.n_input = len(texts)
            run.add_usage(input_tokens=int(sum(len(t) for t in texts) / 4))

        sims = (E @ ex.T).max(axis=1)
        cutoff = max(float(np.quantile(sims, 1 - EMBED_TOP_FRACTION)), EMBED_MIN_SIM)
        emb_hit = sims >= cutoff
        print(f"  embedding gate: {int(emb_hit.sum())} hits "
              f"({emb_hit.mean():.1%}) at cosine >= {cutoff:.3f}")

        np.save(Path("data") / "embeddings.npy", E)   # gitignored, offline only
        print("  saved data/embeddings.npy (LOCAL ONLY — never deployed)")

    passed = lex | emb_hit
    print(f"\n  UNION passed  : {int(passed.sum())} ({passed.mean():.1%})")
    print(f"  lexicon only  : {int((lex & ~emb_hit).sum())}")
    print(f"  embedding only: {int((emb_hit & ~lex).sum())}  <- would be lost to a lexicon-only filter")

    run_id = f"prefilter-{rmod._now()}"
    con.executemany(
        "INSERT OR REPLACE INTO prefilter (record_id, passed, lexicon_hit,"
        " embed_score, embed_hit, run_id) VALUES (?,?,?,?,?,?)",
        [(r["record_id"], int(p), int(l), float(s), int(e), run_id)
         for r, p, l, s, e in zip(rows, passed, lex, sims, emb_hit)])

    # A rejected record is MARKED, not deleted -- Appendix B needs to be able
    # to sample prefilter-rejected records into the gold set.
    con.executemany(
        "INSERT OR IGNORE INTO exclusions (record_id, source, stage, reason, detail, run_id)"
        " VALUES (?,?,?,?,?,?)",
        [(r["record_id"], r["source"], "prefilter", "prefilter",
          f"cosine={s:.3f}, lexicon=0", run_id)
         for r, p, s in zip(rows, passed, sims) if not p])
    con.commit()

    print(f"\n  {int((~passed).sum())} records marked prefilter-rejected "
          f"(retained in `records` for gold sampling — Appendix B)")

    by_src = con.execute("""
        SELECT r.source, count(*) AS n, sum(p.passed) AS passed
        FROM prefilter p JOIN records r ON r.record_id=p.record_id
        WHERE p.run_id=? GROUP BY r.source ORDER BY n DESC""", (run_id,)).fetchall()
    print(f"\n  {'source':<10} {'records':>8} {'passed':>8} {'rate':>7}")
    for s, n, p in by_src:
        print(f"  {s:<10} {n:>8,} {p:>8,} {p / n:>6.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
